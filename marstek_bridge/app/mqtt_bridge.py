"""MQTT-Anbindung (paho-mqtt v2) inkl. Verfuegbarkeit und Command-Queue."""

from __future__ import annotations

import json
import logging
import queue
import socket
import threading
import time
from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger("marstek.mqtt")

PAYLOAD_ONLINE = "online"
PAYLOAD_OFFLINE = "offline"


class MqttBridge:
    """Duenner Wrapper um paho-mqtt mit Reconnect und Zustandsmeldung."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        client_id: str,
        availability_topic: str,
        on_connection_change: Callable[[bool], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.availability_topic = availability_topic
        self._on_connection_change = on_connection_change

        self.commands: queue.Queue[tuple[str, str]] = queue.Queue()
        self._connected = threading.Event()
        self._subscriptions: list[str] = []

        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            clean_session=True,
        )
        if username:
            self._client.username_pw_set(username, password or None)
        self._client.will_set(
            availability_topic, PAYLOAD_OFFLINE, qos=1, retain=True
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

    # ------------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def connect(self, timeout: float = 15.0) -> bool:
        """Verbindung aufbauen und auf CONNACK warten."""
        _LOGGER.info("Verbinde mit MQTT-Broker %s:%s", self.host, self.port)
        try:
            self._client.connect_async(self.host, self.port, keepalive=30)
            self._client.loop_start()
        except (OSError, socket.gaierror) as err:
            _LOGGER.error("MQTT-Verbindungsaufbau fehlgeschlagen: %s", err)
            return False
        return self._connected.wait(timeout)

    def wait_connected(self, timeout: float) -> bool:
        return self._connected.wait(timeout)

    def disconnect(self) -> None:
        try:
            self.publish(self.availability_topic, PAYLOAD_OFFLINE, retain=True)
            time.sleep(0.2)
            self._client.loop_stop()
            self._client.disconnect()
        except Exception as err:  # pragma: no cover - beim Shutdown egal
            _LOGGER.debug("Fehler beim Trennen: %s", err)

    # ------------------------------------------------------------------
    def subscribe(self, topic: str) -> None:
        if topic not in self._subscriptions:
            self._subscriptions.append(topic)
        if self.connected:
            self._client.subscribe(topic, qos=1)
            _LOGGER.debug("Abonniert: %s", topic)

    def publish(
        self, topic: str, payload: Any, *, retain: bool = False, qos: int = 0
    ) -> None:
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload, separators=(",", ":"))
        elif isinstance(payload, bool):
            payload = "ON" if payload else "OFF"
        elif payload is None:
            payload = ""
        else:
            payload = str(payload)
        _LOGGER.trace("MQTT TX %s %s", topic, payload)  # type: ignore[attr-defined]
        self._client.publish(topic, payload, qos=qos, retain=retain)

    def set_available(self, available: bool) -> None:
        self.publish(
            self.availability_topic,
            PAYLOAD_ONLINE if available else PAYLOAD_OFFLINE,
            retain=True,
            qos=1,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _rc_failed(reason_code: Any) -> bool:
        """paho v2 liefert ReasonCode-Objekte, aeltere Broker/Pfade ints."""
        if hasattr(reason_code, "is_failure"):
            return bool(reason_code.is_failure)
        try:
            return int(reason_code) != 0
        except (TypeError, ValueError):  # pragma: no cover - defensiv
            return False

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if self._rc_failed(reason_code):
            _LOGGER.error("MQTT-Verbindung abgelehnt: %s", reason_code)
            return
        _LOGGER.info("MQTT verbunden (%s:%s)", self.host, self.port)
        self._connected.set()
        for topic in self._subscriptions:
            client.subscribe(topic, qos=1)
            _LOGGER.debug("Abonniert: %s", topic)
        if self._on_connection_change:
            self._on_connection_change(True)

    def _on_disconnect(self, client, userdata, disconnect_flags=None, reason_code=None, properties=None):
        self._connected.clear()
        _LOGGER.warning("MQTT-Verbindung verloren (%s) - reconnect laeuft", reason_code)
        if self._on_connection_change:
            self._on_connection_change(False)

    def _on_message(self, client, userdata, message):
        try:
            payload = message.payload.decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - defensiv
            payload = ""
        _LOGGER.trace("MQTT RX %s %s", message.topic, payload)  # type: ignore[attr-defined]
        self.commands.put((message.topic, payload))
