"""Laden, Validieren und Zurueckschreiben der Add-on Konfiguration."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

OPTIONS_PATH = Path(os.environ.get("MARSTEK_OPTIONS", "/data/options.json"))
STATE_PATH = Path(os.environ.get("MARSTEK_STATE", "/data/marstek_state.json"))
SUPERVISOR_URL = "http://supervisor/addons/self/options"

DEFAULTS: dict[str, Any] = {
    # Geraet
    "device_ip": "192.168.0.45",
    "device_udp_port": 30000,
    "device_ble_mac": "",
    "device_type": "",
    "local_udp_port": 0,
    # MQTT
    "mqtt_host": "core-mosquitto",
    "mqtt_port": 1883,
    "mqtt_username": "mqtt-marstek",
    "mqtt_password": "mqtt-marstek",
    "mqtt_discovery_prefix": "homeassistant",
    "mqtt_base_topic": "Marstek-Bridge-Control",
    "mqtt_suggested_area": "Marstek",
    # Kommunikation
    "request_delay": 1.0,
    "request_timeout": 1.0,
    "request_retries": 2,
    "request_max_time": 10.0,
    "poll_interval": 30,
    "poll_enabled": True,
    "enable_em": False,
    # Initialwerte
    "dod_value": 88,
    "ble_block_enable": True,
    "led_state": False,
    # Passive Mode
    "passive_power_min": -1200,
    "passive_power_max": 1200,
    "passive_power_default": 0,
    "passive_cd_time_max": 300,
    "passive_cd_time_default": 10,
    "passive_keepalive": False,
    # Betrieb
    "watchdog_failure_threshold": 3,
    "persist_device_info": True,
    "health_port": 8099,
    "log_level": "info",
}

_LOGGER = logging.getLogger("marstek.settings")


@dataclass
class Settings:
    """Typisierte Sicht auf die Add-on Optionen."""

    raw: dict[str, Any] = field(default_factory=dict)

    # -- Geraet ------------------------------------------------------------
    device_ip: str = DEFAULTS["device_ip"]
    device_udp_port: int = DEFAULTS["device_udp_port"]
    device_ble_mac: str = ""
    device_type: str = ""
    local_udp_port: int = 0

    # -- MQTT --------------------------------------------------------------
    mqtt_host: str = DEFAULTS["mqtt_host"]
    mqtt_port: int = DEFAULTS["mqtt_port"]
    mqtt_username: str = DEFAULTS["mqtt_username"]
    mqtt_password: str = DEFAULTS["mqtt_password"]
    mqtt_discovery_prefix: str = DEFAULTS["mqtt_discovery_prefix"]
    mqtt_base_topic: str = DEFAULTS["mqtt_base_topic"]
    mqtt_suggested_area: str = DEFAULTS["mqtt_suggested_area"]

    # -- Kommunikation -----------------------------------------------------
    request_delay: float = 1.0
    request_timeout: float = 1.0
    request_retries: int = 2
    request_max_time: float = 10.0
    poll_interval: int = 30
    poll_enabled: bool = True
    enable_em: bool = False

    # -- Initialwerte ------------------------------------------------------
    dod_value: int = 88
    ble_block_enable: bool = True
    led_state: bool = False

    # -- Passive -----------------------------------------------------------
    passive_power_min: int = -1200
    passive_power_max: int = 1200
    passive_power_default: int = 0
    passive_cd_time_max: int = 300
    passive_cd_time_default: int = 10
    passive_keepalive: bool = False

    # -- Betrieb -----------------------------------------------------------
    watchdog_failure_threshold: int = 3
    persist_device_info: bool = True
    health_port: int = 8099
    log_level: str = "info"

    # ---------------------------------------------------------------------
    @property
    def base_topic(self) -> str:
        return self.mqtt_base_topic.strip("/")

    @property
    def availability_topic(self) -> str:
        return f"{self.base_topic}/status"

    def uid(self) -> str:
        """Stabile Kennung fuer unique_id / Discovery-Node."""
        if self.device_ble_mac:
            return self.device_ble_mac.replace(":", "").lower()
        return self.device_ip.replace(".", "_")

    # ---------------------------------------------------------------------
    def persist_device_info_values(self, ble_mac: str, device_type: str) -> None:
        """ble_mac und device_type dauerhaft sichern.

        1. lokaler State-File (immer, funktioniert auch ohne Supervisor)
        2. Add-on Optionen via Supervisor API (damit die Werte auch in der
           Add-on Konfigurationsseite stehen)
        """
        changed = False
        if ble_mac and ble_mac != self.device_ble_mac:
            self.device_ble_mac = ble_mac
            changed = True
        if device_type and device_type != self.device_type:
            self.device_type = device_type
            changed = True
        if not changed:
            return

        _write_state(
            {"device_ble_mac": self.device_ble_mac, "device_type": self.device_type}
        )
        _LOGGER.info(
            "Geraetedaten gesichert: device_type=%s ble_mac=%s",
            self.device_type,
            self.device_ble_mac,
        )

        if self.persist_device_info:
            self.raw["device_ble_mac"] = self.device_ble_mac
            self.raw["device_type"] = self.device_type
            _push_options_to_supervisor(self.raw)


# -------------------------------------------------------------------------
def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:  # pragma: no cover - defensiv
        _LOGGER.warning("Konnte %s nicht lesen: %s", path, err)
    return {}


def _write_state(data: dict[str, Any]) -> None:
    try:
        current = _read_json(STATE_PATH)
        current.update(data)
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    except OSError as err:  # pragma: no cover - defensiv
        _LOGGER.warning("Konnte State-File nicht schreiben: %s", err)


def _push_options_to_supervisor(options: dict[str, Any]) -> None:
    """Optionen ueber die Supervisor API zurueckschreiben."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        _LOGGER.debug("Kein SUPERVISOR_TOKEN - ueberspringe Options-Rueckschreibung")
        return
    payload = json.dumps({"options": options}).encode("utf-8")
    req = urllib.request.Request(
        SUPERVISOR_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            _LOGGER.info(
                "Add-on Optionen aktualisiert (HTTP %s)", getattr(resp, "status", "?")
            )
    except (urllib.error.URLError, OSError) as err:
        _LOGGER.warning("Options-Rueckschreibung fehlgeschlagen: %s", err)


def _coerce(value: Any, default: Any) -> Any:
    if isinstance(default, bool):
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    if isinstance(default, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return "" if value is None else str(value)


def load_settings() -> Settings:
    """Optionen laden: Defaults < options.json < ENV (MARSTEK_*)."""
    merged: dict[str, Any] = dict(DEFAULTS)
    merged.update(_read_json(OPTIONS_PATH))

    for key in DEFAULTS:
        env_val = os.environ.get(f"MARSTEK_{key.upper()}")
        if env_val is not None:
            merged[key] = env_val

    clean = {key: _coerce(merged.get(key), DEFAULTS[key]) for key in DEFAULTS}

    settings = Settings(raw=dict(clean))
    for key, value in clean.items():
        setattr(settings, key, value)

    # Persistierte Geraetedaten nachziehen, falls in den Optionen leer.
    state = _read_json(STATE_PATH)
    if not settings.device_ble_mac and state.get("device_ble_mac"):
        settings.device_ble_mac = str(state["device_ble_mac"])
    if not settings.device_type and state.get("device_type"):
        settings.device_type = str(state["device_type"])

    # Plausibilitaet
    settings.passive_power_default = max(
        settings.passive_power_min,
        min(settings.passive_power_max, settings.passive_power_default),
    )
    settings.passive_cd_time_default = max(
        0, min(settings.passive_cd_time_max, settings.passive_cd_time_default)
    )
    settings.dod_value = max(30, min(88, settings.dod_value))
    return settings
