"""Kernlogik der Marstek MQTT - UDP Bridge."""

from __future__ import annotations

import json
import logging
import queue
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from . import __project__, __version__
from .const import (
    COMM_FAIL,
    COMM_OK,
    GROUP_TITLES,
    GRP_BATTERY,
    GRP_ENERGY_CONTROL,
    GRP_ENERGY_METER,
    GRP_ENERGY_MODE,
    GRP_ENERGY_STATUS,
    GRP_PV,
    GRP_SYSTEM,
    M_BAT_STATUS,
    M_BLE_ADV,
    M_BLE_STATUS,
    M_DOD_SET,
    M_EM_STATUS,
    M_ES_MODE,
    M_ES_SET_MODE,
    M_ES_STATUS,
    M_GET_DEVICE,
    M_LED_CTRL,
    M_PV_STATUS,
    M_WIFI_STATUS,
    MODE_AI,
    MODE_AUTO,
    MODE_PASSIVE,
    MODE_UPS,
    SELECTABLE_MODES,
)
from .entities import (
    BATTERY_ENTITIES,
    ENERGY_METER_ENTITIES,
    ENERGY_MODE_ENTITIES,
    ENERGY_STATUS_ENTITIES,
    SYSTEM_ENTITIES,
    DiscoveryBuilder,
    Ent,
    build_control_entities,
    build_pv_entities,
)
from .health import HealthState
from .mqtt_bridge import MqttBridge
from .settings import Settings, load_state, save_state
from .udp_client import ApiError, MarstekUdpClient, UdpError

_LOGGER = logging.getLogger("marstek.bridge")


def _utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Bridge:
    """Verbindet die lokale Marstek UDP-API mit MQTT / Home Assistant."""

    def __init__(self, settings: Settings, health: HealthState) -> None:
        self.s = settings
        self.health = health
        self._running = True
        self._initialized = False
        self._watchdog_failures = 0
        self._discovered: set[str] = set()
        self._last_poll = 0.0
        self._last_passive_push = 0.0
        self._last_regulation_send = 0.0
        self._last_regulation_input: float | None = None
        self._pending_regulation: float | None = None
        # Eigener PV-Energiezaehler: Summe in Wh plus letzte Stuetzstelle
        # (Zeitpunkt, Leistung) fuer die Trapezintegration.
        self._pv_energy_wh = float(load_state().get("pv_energy_wh") or 0.0)
        self._pv_last_sample: tuple[float, float] | None = None

        self.states: dict[str, dict[str, Any]] = {
            GRP_SYSTEM: {},
            GRP_BATTERY: {},
            GRP_PV: {},
            GRP_ENERGY_STATUS: {},
            GRP_ENERGY_MODE: {},
            GRP_ENERGY_CONTROL: {},
            GRP_ENERGY_METER: {},
        }

        self.udp = MarstekUdpClient(
            settings.device_ip,
            settings.device_udp_port,
            local_port=settings.local_udp_port,
            timeout=settings.request_timeout,
            retries=settings.request_retries,
            max_time=settings.request_max_time,
        )
        self.mqtt = MqttBridge(
            host=settings.mqtt_host,
            port=settings.mqtt_port,
            username=settings.mqtt_username,
            password=settings.mqtt_password,
            client_id=f"marstek-bridge-{settings.uid()}",
            availability_topic=settings.availability_topic,
            on_connection_change=self._on_mqtt_change,
        )
        self.disc: DiscoveryBuilder | None = None

        # Sollwerte der Steuerung
        self.states[GRP_ENERGY_CONTROL] = {
            "target_mode": MODE_AUTO,
            "passive_power": settings.passive_power_default,
            "passive_cd_time": settings.passive_cd_time_default,
            "applied_mode": None,
            "self_regulation": settings.self_regulation_enabled,
            "regulation_input": None,
            "regulation_output": None,
        }
        self.states[GRP_SYSTEM].update(
            {
                "communication": COMM_FAIL,
                "comm_ok": False,
                "dod_value": settings.dod_value,
                "ble_block": settings.ble_block_enable,
                "led_state": settings.led_state,
                "last_set_result": None,
                "last_update": None,
            }
        )

    # =================================================================
    # Lifecycle
    # =================================================================
    def run(self) -> None:
        _LOGGER.info("\033[1m%s\033[0m v%s", __project__, __version__)
        _LOGGER.info(
            "Geraet %s:%s | MQTT %s:%s | Base-Topic '%s'",
            self.s.device_ip,
            self.s.device_udp_port,
            self.s.mqtt_host,
            self.s.mqtt_port,
            self.s.base_topic,
        )
        _LOGGER.info(
            "Timing: delay=%ss timeout=%ss retries=%s max=%ss poll=%ss",
            self.s.request_delay,
            self.s.request_timeout,
            self.s.request_retries,
            self.s.request_max_time,
            self.s.poll_interval,
        )

        if self.s.self_regulation_enabled:
            _LOGGER.info(
                "Selbstregelung aktiv - Topic '%s', Reserve %s W, "
                "Schritt hoch %.0f%% / max %s W, runter %s",
                self.regulation_topic,
                self.s.self_regulation_reserve,
                self.s.self_regulation_step_gain * 100,
                self.s.self_regulation_step_up,
                "ungebremst" if self.s.self_regulation_step_down <= 0
                else f"max {self.s.self_regulation_step_down} W",
            )

        if not self._connect_mqtt_blocking():
            return

        while self._running:
            try:
                if not self._initialized:
                    self._initialize()
                self._main_loop_tick()
            except KeyboardInterrupt:  # pragma: no cover
                break
            except Exception as err:  # pragma: no cover - Sicherheitsnetz
                _LOGGER.exception("Unerwarteter Fehler in der Hauptschleife: %s", err)
                self._sleep(5.0)

        self.shutdown()

    def stop(self) -> None:
        _LOGGER.info("Beende Bridge ...")
        self._running = False

    def shutdown(self) -> None:
        try:
            self._set_communication(False, "shutdown")
        except Exception:  # pragma: no cover
            pass
        self.mqtt.disconnect()
        self.udp.close()

    # =================================================================
    # MQTT
    # =================================================================
    def _on_mqtt_change(self, connected: bool) -> None:
        self.health.update(mqtt_connected=connected)
        if connected and self.disc is not None:
            # Nach einem Reconnect Verfuegbarkeit und States erneut senden.
            self.mqtt.set_available(True)
            self._publish_all_states()

    def _connect_mqtt_blocking(self) -> bool:
        """MQTT-Verbindung aufbauen; ohne Broker laeuft gar nichts."""
        backoff = 2.0
        while self._running:
            if self.mqtt.connect(timeout=15.0):
                self.health.update(mqtt_connected=True)
                self.mqtt.set_available(True)
                self._subscribe_commands()
                return True
            self.health.update(
                mqtt_connected=False, last_error="MQTT nicht erreichbar"
            )
            _LOGGER.error(
                "MQTT-Broker nicht erreichbar - neuer Versuch in %.0fs "
                "(Watchdog meldet unhealthy)",
                backoff,
            )
            self._sleep(backoff)
            backoff = min(backoff * 2, 60.0)
        return False

    def _subscribe_commands(self) -> None:
        base = self.s.base_topic
        for topic in (
            f"{base}/{GRP_SYSTEM}/dod/set",
            f"{base}/{GRP_SYSTEM}/ble_block/set",
            f"{base}/{GRP_SYSTEM}/led/set",
            f"{base}/{GRP_ENERGY_CONTROL}/mode/set",
            f"{base}/{GRP_ENERGY_CONTROL}/passive_power/set",
            f"{base}/{GRP_ENERGY_CONTROL}/passive_cd_time/set",
            f"{base}/{GRP_ENERGY_CONTROL}/apply/set",
            f"{base}/{GRP_ENERGY_CONTROL}/refresh/set",
            # Eigener Refresh-Button je Statusgruppe
            f"{base}/{GRP_BATTERY}/refresh/set",
            f"{base}/{GRP_PV}/refresh/set",
            f"{base}/{GRP_ENERGY_STATUS}/refresh/set",
            f"{base}/{GRP_ENERGY_MODE}/refresh/set",
            f"{base}/{GRP_ENERGY_METER}/refresh/set",
            f"{base}/{GRP_ENERGY_CONTROL}/self_regulation/set",
            self.regulation_topic,
        ):
            self.mqtt.subscribe(topic)

    # =================================================================
    # Initialisierung
    # =================================================================
    def _initialize(self) -> None:
        _LOGGER.info("\033[1mStarte Initialisierungssequenz\033[0m")
        steps: list[tuple[str, Callable[[], bool]]] = [
            (M_GET_DEVICE, self._step_get_device),
            (M_WIFI_STATUS, self._step_wifi),
            (M_BAT_STATUS, self._step_battery),
            (M_PV_STATUS, self._step_pv),
            (M_ES_STATUS, self._step_es_status),
            (M_BLE_STATUS, self._step_ble),
            (M_DOD_SET, lambda: self._set_dod(self.s.dod_value)),
            (M_BLE_ADV, lambda: self._set_ble_block(self.s.ble_block_enable)),
            (M_LED_CTRL, lambda: self._set_led(self.s.led_state)),
            (M_ES_MODE, self._step_es_mode),
        ]
        if self.s.enable_em:
            steps.append((M_EM_STATUS, self._step_em))

        ok = True
        for index, (label, func) in enumerate(steps, start=1):
            if not self._running:
                return
            _LOGGER.info("[%s/%s] %s", index, len(steps), label)
            if not func():
                ok = False
            if index < len(steps):
                self._sleep_with_commands(self.s.request_delay)

        if ok:
            self._initialized = True
            self.health.update(initialized=True)
            self._set_communication(True)
            _LOGGER.info(
                "\033[1;32mInitialisierung abgeschlossen - "
                "Communication established = ON\033[0m"
            )
        else:
            self._set_communication(False, "Initialisierung unvollstaendig")
            _LOGGER.error(
                "Initialisierung unvollstaendig - neuer Versuch in %.0fs",
                max(5.0, self.s.poll_interval),
            )
            self._sleep_with_commands(max(5.0, float(self.s.poll_interval)))

    # -- einzelne Schritte ---------------------------------------------
    def _step_get_device(self) -> bool:
        try:
            result = self.udp.discover(self.s.device_ble_mac or None)
        except UdpError as err:
            self._handle_udp_error(M_GET_DEVICE, err)
            return False

        self.states[GRP_SYSTEM].update(
            {
                "device": result.get("device"),
                "ver": result.get("ver"),
                "ble_mac": result.get("ble_mac"),
                "wifi_mac": result.get("wifi_mac"),
                "ssid": result.get("wifi_name") or self.states[GRP_SYSTEM].get("ssid"),
                "ip": result.get("ip") or self.s.device_ip,
            }
        )
        self.s.persist_device_info_values(
            str(result.get("ble_mac") or ""), str(result.get("device") or "")
        )
        self._ensure_discovery_builder(result.get("ver"))
        self._publish_group(GRP_SYSTEM, SYSTEM_ENTITIES)
        self._publish_group(GRP_ENERGY_CONTROL, self._control_entities())
        return True

    def _step_wifi(self) -> bool:
        result = self._query(M_WIFI_STATUS)
        if result is None:
            return False
        self.states[GRP_SYSTEM].update(
            {
                "wifi_mac": result.get("wifi_mac", self.states[GRP_SYSTEM].get("wifi_mac")),
                "ssid": result.get("ssid"),
                "rssi": result.get("rssi"),
                "ip": result.get("sta_ip") or self.states[GRP_SYSTEM].get("ip"),
                "sta_gate": result.get("sta_gate"),
                "sta_mask": result.get("sta_mask"),
                "sta_dns": result.get("sta_dns"),
            }
        )
        self._publish_group(GRP_SYSTEM, SYSTEM_ENTITIES)
        return True

    def _step_ble(self) -> bool:
        result = self._query(M_BLE_STATUS)
        if result is None:
            return False
        self.states[GRP_SYSTEM].update(
            {
                "ble_state": result.get("state"),
                "ble_mac": result.get("ble_mac", self.states[GRP_SYSTEM].get("ble_mac")),
            }
        )
        self._publish_group(GRP_SYSTEM, SYSTEM_ENTITIES)
        return True

    def _step_battery(self) -> bool:
        result = self._query(M_BAT_STATUS)
        if result is None:
            return False
        self.states[GRP_BATTERY] = _clean(result)
        self._publish_group(GRP_BATTERY, BATTERY_ENTITIES)
        return True

    def _step_pv(self) -> bool:
        result = self._query(M_PV_STATUS)
        if result is None:
            return False
        clean = _clean(result)
        self.states[GRP_PV] = clean
        self._publish_group(GRP_PV, build_pv_entities(clean))
        return True

    def _step_es_status(self) -> bool:
        result = self._query(M_ES_STATUS)
        if result is None:
            return False
        clean = _clean(result)
        self.states[GRP_ENERGY_STATUS] = clean
        self._update_pv_energy(clean.get("pv_power"))
        self._publish_group(GRP_ENERGY_STATUS, ENERGY_STATUS_ENTITIES)
        return True

    def _update_pv_energy(self, power: Any) -> None:
        """Eigenen PV-Energiezaehler aus pv_power fortschreiben.

        Der Zaehler des Geraets (total_pv_energy) ist unzuverlaessig, deshalb
        wird hier ueber die tatsaechlich vergangene Zeit integriert - als
        Trapez, weil die Abfrage nicht in exakt gleichen Abstaenden kommt.
        """
        if not self.s.pv_energy_enabled:
            return
        if not isinstance(power, (int, float)) or isinstance(power, bool):
            _LOGGER.debug("PV-Energie: kein gueltiger pv_power-Wert (%r)", power)
            return

        now = time.monotonic()
        power = float(power)
        previous = self._pv_last_sample
        self._pv_last_sample = (now, power)
        self.states[GRP_ENERGY_STATUS]["calc_pv_energy"] = round(self._pv_energy_wh, 2)

        if previous is None:
            _LOGGER.debug(
                "PV-Energie: erste Stuetzstelle (%.0f W), Zaehlerstand %.1f Wh",
                power,
                self._pv_energy_wh,
            )
            return

        last_time, last_power = previous
        delta = now - last_time
        if delta <= 0:
            return
        if delta > self.s.pv_energy_max_gap:
            _LOGGER.warning(
                "PV-Energie: Luecke von %.0fs ueberschreitet pv_energy_max_gap "
                "(%ss) - Intervall wird verworfen",
                delta,
                self.s.pv_energy_max_gap,
            )
            return

        added = (last_power + power) / 2.0 * delta / 3600.0
        self._pv_energy_wh += added
        self.states[GRP_ENERGY_STATUS]["calc_pv_energy"] = round(self._pv_energy_wh, 2)
        _LOGGER.debug(
            "PV-Energie: %.0f W -> %.0f W ueber %.1fs = +%.3f Wh (gesamt %.1f Wh)",
            last_power,
            power,
            delta,
            added,
            self._pv_energy_wh,
        )
        save_state({"pv_energy_wh": round(self._pv_energy_wh, 3)})

    def _step_es_mode(self) -> bool:
        result = self._query(M_ES_MODE)
        if result is None:
            return False
        clean = _clean(result)
        for key in ("input_energy", "output_energy"):
            if isinstance(clean.get(key), (int, float)):
                clean[key] = round(clean[key] * 0.1, 1)
        self.states[GRP_ENERGY_MODE] = clean

        mode = clean.get("mode")
        if isinstance(mode, str) and mode in SELECTABLE_MODES:
            if self.states[GRP_ENERGY_CONTROL].get("applied_mode") is None:
                self.states[GRP_ENERGY_CONTROL]["target_mode"] = mode
                self._publish_state(GRP_ENERGY_CONTROL)
        self._publish_group(GRP_ENERGY_MODE, ENERGY_MODE_ENTITIES)
        return True

    def _step_em(self) -> bool:
        result = self._query(M_EM_STATUS)
        if result is None:
            return False
        clean = _clean(result)
        for key in ("input_energy", "output_energy"):
            if isinstance(clean.get(key), (int, float)):
                clean[key] = round(clean[key] * 0.1, 1)
        self.states[GRP_ENERGY_METER] = clean
        self._publish_group(GRP_ENERGY_METER, ENERGY_METER_ENTITIES)
        return True

    # =================================================================
    # Steuerbefehle
    # =================================================================
    def _set_dod(self, value: int) -> bool:
        value = max(30, min(88, int(value)))
        result = self._query(M_DOD_SET, {"value": value}, with_instance=False)
        if result is None:
            return False
        self.states[GRP_SYSTEM]["dod_value"] = value
        self._note_set_result(M_DOD_SET, result)
        self._publish_state(GRP_SYSTEM)
        return True

    def _set_ble_block(self, enabled: bool) -> bool:
        # Doku 3.9: "enable: 0 = enable, 1 = disable" (Beispiel sendet 0),
        # d. h. 0 aktiviert die Bluetooth-Sperre.
        result = self._query(
            M_BLE_ADV, {"enable": 0 if enabled else 1}, with_instance=False
        )
        if result is None:
            return False
        self.states[GRP_SYSTEM]["ble_block"] = bool(enabled)
        self._note_set_result(M_BLE_ADV, result)
        self._publish_state(GRP_SYSTEM)
        return True

    def _set_led(self, on: bool) -> bool:
        result = self._query(
            M_LED_CTRL, {"state": 1 if on else 0}, with_instance=False
        )
        if result is None:
            return False
        self.states[GRP_SYSTEM]["led_state"] = bool(on)
        self._note_set_result(M_LED_CTRL, result)
        self._publish_state(GRP_SYSTEM)
        return True

    def _build_mode_config(self, mode: str) -> dict[str, Any]:
        ctrl = self.states[GRP_ENERGY_CONTROL]
        if mode == MODE_AUTO:
            return {"mode": MODE_AUTO, "auto_cfg": {"enable": 1}}
        if mode == MODE_AI:
            return {"mode": MODE_AI, "ai_cfg": {"enable": 1}}
        if mode == MODE_UPS:
            return {"mode": MODE_UPS, "ups_cfg": {"enable": 1}}
        if mode == MODE_PASSIVE:
            cd = int(ctrl.get("passive_cd_time", self.s.passive_cd_time_default))
            cd = max(0, min(self.s.passive_cd_time_max, cd))
            return {
                "mode": MODE_PASSIVE,
                "passive_cfg": {
                    "power": self._effective_passive_power(),
                    "cd_time": cd,
                },
            }
        raise ValueError(f"Unbekannter Modus: {mode}")

    def _apply_mode(self, refresh: bool = True) -> bool:
        """Den vorgemerkten Modus an das Geraet senden.

        ``refresh=False`` laesst das anschliessende ES.GetMode weg - das nutzt
        die Selbstregelung, damit pro Regelschritt nur ein Kommando laeuft.
        """
        mode = str(self.states[GRP_ENERGY_CONTROL].get("target_mode") or MODE_AUTO)
        try:
            config = self._build_mode_config(mode)
        except ValueError as err:
            _LOGGER.error("%s", err)
            return False

        _LOGGER.info("\033[1;36mES.SetMode -> %s\033[0m %s", mode, config)
        result = self._query(M_ES_SET_MODE, {"config": config})
        if result is None:
            return False
        self.states[GRP_ENERGY_CONTROL]["applied_mode"] = mode
        self._note_set_result(M_ES_SET_MODE, result)
        self._publish_state(GRP_ENERGY_CONTROL)
        self._last_passive_push = time.monotonic()
        if refresh:
            self._sleep_with_commands(self.s.request_delay)
            self._step_es_mode()
        return True

    # =================================================================
    # Selbstregelung (Passive)
    # =================================================================
    @property
    def regulation_topic(self) -> str:
        """Topic, auf dem der gefilterte Regelwert erwartet wird."""
        custom = (self.s.self_regulation_topic or "").strip()
        return custom or f"{self.s.base_topic}/{GRP_ENERGY_CONTROL}/regulation_input"

    def _regulation_active(self) -> bool:
        return bool(self.states[GRP_ENERGY_CONTROL].get("self_regulation"))

    def _effective_passive_power(self) -> int:
        """Leistung, die tatsaechlich im Passive-Kommando landet.

        Ohne Selbstregelung ist das der Wert der Number-Entity. Mit
        Selbstregelung ist die Number-Entity die Obergrenze und der geregelte
        Wert wird gesendet.
        """
        ctrl = self.states[GRP_ENERGY_CONTROL]
        if self._regulation_active():
            value = ctrl.get("regulation_output")
            if value is None:
                _LOGGER.info(
                    "Selbstregelung aktiv, aber noch kein Regelwert empfangen "
                    "- es werden 0 W gesendet"
                )
                return 0
            return int(value)
        power = int(ctrl.get("passive_power", 0))
        return max(self.s.passive_power_min, min(self.s.passive_power_max, power))

    def _set_self_regulation(self, enabled: bool) -> None:
        ctrl = self.states[GRP_ENERGY_CONTROL]
        ctrl["self_regulation"] = enabled
        _LOGGER.info(
            "\033[1;36mSelbstregelung %s\033[0m",
            "aktiviert" if enabled else "deaktiviert",
        )
        if not enabled:
            ctrl["regulation_output"] = None
            self._pending_regulation = None
        self._publish_state(GRP_ENERGY_CONTROL)
        if enabled and ctrl.get("regulation_input") is not None:
            self._pending_regulation = float(ctrl["regulation_input"])
            self._flush_regulation()

    @staticmethod
    def _parse_number(payload: str) -> float | None:
        """Zahl aus einem MQTT-Payload lesen: roh, JSON-Zahl oder JSON-Objekt."""
        text = payload.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            pass
        try:
            data = json.loads(text)
        except ValueError:
            return None
        if isinstance(data, (int, float)):
            return float(data)
        if isinstance(data, dict):
            for key in ("value", "state", "power", "p"):
                candidate = data.get(key)
                if isinstance(candidate, (int, float)):
                    return float(candidate)
                if isinstance(candidate, str):
                    try:
                        return float(candidate.strip())
                    except ValueError:
                        continue
        return None

    def _on_regulation_value(self, payload: str) -> None:
        value = self._parse_number(payload)
        if value is None:
            _LOGGER.warning("Regelwert nicht lesbar: %r", payload[:80])
            return
        ctrl = self.states[GRP_ENERGY_CONTROL]
        ctrl["regulation_input"] = round(value, 1)
        self._last_regulation_input = time.monotonic()
        self._publish_state(GRP_ENERGY_CONTROL)

        if not self._regulation_active():
            _LOGGER.trace("Regelwert %.1f W empfangen, Selbstregelung aus", value)
            return
        if ctrl.get("applied_mode") != MODE_PASSIVE:
            _LOGGER.debug(
                "Regelwert %.1f W empfangen, aber Passive ist nicht aktiv", value
            )
            return
        self._pending_regulation = value
        self._flush_regulation()

    def _compute_regulation_output(self, value: float) -> int:
        """Aus der Netzleistung den naechsten Sollwert berechnen.

        Der Regelkreis arbeitet bewusst asymmetrisch:

        * **hoch** (zu viel Netzbezug) wird gebremst - pro Schritt nur ein
          Anteil der Abweichung (``step_gain``) und hoechstens ``step_up`` Watt.
          Ein zu grosser Sprung nach oben wuerde ueberschiessen und damit
          Einspeisung ins Netz verursachen.
        * **runter** (zu wenig Netzbezug) geschieht in voller Hoehe, weil das
          immer die sichere Richtung ist.

        Nach unten wird bei 0 W begrenzt, nach oben durch die Number-Entity
        *Passive power*. Da immer der bereits begrenzte Sollwert die Basis des
        naechsten Schritts ist, kann der Regler nicht ueber den Deckel
        hinauslaufen (kein Windup).
        """
        ctrl = self.states[GRP_ENERGY_CONTROL]
        cap = max(0, min(self.s.passive_power_max, int(ctrl.get("passive_power", 0))))
        base = int(ctrl.get("regulation_output") or 0)
        error = value - self.s.self_regulation_reserve

        if error > 0:
            step = min(error * self.s.self_regulation_step_gain,
                       float(self.s.self_regulation_step_up))
        else:
            step = error
            if self.s.self_regulation_step_down > 0:
                step = max(step, -float(self.s.self_regulation_step_down))

        return int(max(0, min(cap, round(base + step))))

    def _flush_regulation(self) -> None:
        """Ausstehenden Regelwert senden.

        Ein Schritt nach unten darf Totband und Mindestabstand ueberspringen
        (``self_regulation_fast_down``), damit auf einen plotzlichen Lastabfall
        sofort reagiert wird. Nach oben bleiben beide Bremsen aktiv.
        """
        if self._pending_regulation is None or not self._regulation_active():
            return
        ctrl = self.states[GRP_ENERGY_CONTROL]
        if ctrl.get("applied_mode") != MODE_PASSIVE:
            return

        value = self._pending_regulation
        out = self._compute_regulation_output(value)
        last = ctrl.get("regulation_output")
        going_down = last is not None and out < int(last)
        fast = going_down and self.s.self_regulation_fast_down

        if not fast:
            if (
                time.monotonic() - self._last_regulation_send
                < self.s.self_regulation_min_interval
            ):
                return  # Wert bleibt vorgemerkt und wird spaeter gesendet
            if last is not None and abs(out - int(last)) < self.s.self_regulation_deadband:
                self._pending_regulation = None
                _LOGGER.trace(
                    "Regelwert %.1f W -> %s W innerhalb des Totbands (%s W), "
                    "nicht gesendet",
                    value,
                    out,
                    self.s.self_regulation_deadband,
                )
                return

        self._pending_regulation = None
        ctrl["regulation_output"] = out
        _LOGGER.info(
            "Selbstregelung %s: Netz %.1f W (Ziel %s W) | Sollwert %s -> "
            "\033[1m%s W\033[0m (Deckel %s W)",
            "RUNTER" if going_down else "hoch",
            value,
            self.s.self_regulation_reserve,
            last if last is not None else 0,
            out,
            max(0, int(ctrl.get("passive_power", 0))),
        )
        self._publish_state(GRP_ENERGY_CONTROL)
        if self._apply_mode(refresh=False):
            self._last_regulation_send = time.monotonic()

    def _check_regulation_timeout(self) -> None:
        """Bei ausbleibenden Werten auf 0 W zurueckfallen.

        Ohne das wuerde der Keepalive den zuletzt berechneten Sollwert endlos
        weitersenden, obwohl niemand mehr misst - etwa nach einem HA-Neustart
        oder wenn die publizierende Automation deaktiviert wurde.
        """
        timeout = self.s.self_regulation_input_timeout
        if timeout <= 0 or not self._regulation_active():
            return
        if self._last_regulation_input is None:
            return
        ctrl = self.states[GRP_ENERGY_CONTROL]
        if ctrl.get("applied_mode") != MODE_PASSIVE:
            return
        current = ctrl.get("regulation_output")
        if current is None or int(current) == 0:
            return
        if time.monotonic() - self._last_regulation_input < timeout:
            return

        _LOGGER.warning(
            "Seit %ss kein Regelwert auf '%s' - Sollwert wird auf 0 W gesetzt",
            timeout,
            self.regulation_topic,
        )
        ctrl["regulation_output"] = 0
        self._pending_regulation = None
        self._publish_state(GRP_ENERGY_CONTROL)
        if self._apply_mode(refresh=False):
            self._last_regulation_send = time.monotonic()

    # =================================================================
    # MQTT-Kommandos
    # =================================================================
    def _process_commands(self) -> None:
        while True:
            try:
                topic, payload = self.mqtt.commands.get_nowait()
            except queue.Empty:
                return
            try:
                self._handle_command(topic, payload)
            except Exception as err:  # pragma: no cover - Sicherheitsnetz
                _LOGGER.exception("Fehler bei Kommando %s: %s", topic, err)

    def _handle_command(self, topic: str, payload: str) -> None:
        if topic == self.regulation_topic:
            self._on_regulation_value(payload)
            return
        base = self.s.base_topic
        suffix = topic[len(base) + 1 :] if topic.startswith(base) else topic
        _LOGGER.debug("Kommando %s = %s", suffix, payload)
        ctrl = self.states[GRP_ENERGY_CONTROL]

        if suffix == f"{GRP_SYSTEM}/dod/set":
            self._set_dod(int(float(payload)))
        elif suffix == f"{GRP_SYSTEM}/ble_block/set":
            self._set_ble_block(payload.strip().upper() == "ON")
        elif suffix == f"{GRP_SYSTEM}/led/set":
            self._set_led(payload.strip().upper() == "ON")
        elif suffix == f"{GRP_ENERGY_CONTROL}/mode/set":
            value = payload.strip()
            if value not in SELECTABLE_MODES:
                _LOGGER.warning("Unbekannter Modus '%s' ignoriert", value)
                return
            ctrl["target_mode"] = value
            self._publish_state(GRP_ENERGY_CONTROL)
            _LOGGER.info(
                "Zielmodus '%s' vorgemerkt - mit 'Apply mode' aktivieren", value
            )
        elif suffix == f"{GRP_ENERGY_CONTROL}/passive_power/set":
            value = int(float(payload))
            ctrl["passive_power"] = max(
                self.s.passive_power_min, min(self.s.passive_power_max, value)
            )
            self._publish_state(GRP_ENERGY_CONTROL)
        elif suffix == f"{GRP_ENERGY_CONTROL}/passive_cd_time/set":
            value = int(float(payload))
            ctrl["passive_cd_time"] = max(
                0, min(self.s.passive_cd_time_max, value)
            )
            self._publish_state(GRP_ENERGY_CONTROL)
        elif suffix == f"{GRP_ENERGY_CONTROL}/self_regulation/set":
            self._set_self_regulation(payload.strip().upper() == "ON")
        elif suffix == f"{GRP_ENERGY_CONTROL}/apply/set":
            self._apply_mode()
        elif suffix == f"{GRP_ENERGY_CONTROL}/refresh/set":
            self._poll()
        elif suffix in self._group_refresh_steps():
            self._refresh_group(suffix)
        else:
            _LOGGER.debug("Unbehandeltes Topic: %s", topic)

    def _group_refresh_steps(self) -> dict[str, Callable[[], bool]]:
        """Topic-Suffix -> Abfrage, die der jeweilige Refresh-Button ausloest."""
        return {
            f"{GRP_BATTERY}/refresh/set": self._step_battery,
            f"{GRP_PV}/refresh/set": self._step_pv,
            f"{GRP_ENERGY_STATUS}/refresh/set": self._step_es_status,
            f"{GRP_ENERGY_MODE}/refresh/set": self._step_es_mode,
            f"{GRP_ENERGY_METER}/refresh/set": self._step_em,
        }

    def _refresh_group(self, suffix: str) -> None:
        step = self._group_refresh_steps()[suffix]
        group = suffix.split("/", 1)[0]
        _LOGGER.info("Manuelle Abfrage: %s", GROUP_TITLES[group])
        if step():
            self._set_communication(True)

    # =================================================================
    # Hauptschleife / Polling
    # =================================================================
    def _main_loop_tick(self) -> None:
        self._process_commands()

        if not self.mqtt.connected:
            self.health.update(mqtt_connected=False)
            self._sleep(1.0)
            return

        now = time.monotonic()
        if (
            self._initialized
            and self.s.poll_enabled
            and now - self._last_poll >= self.s.poll_interval
        ):
            self._poll()

        self._flush_regulation()
        self._check_regulation_timeout()
        self._passive_keepalive()
        self._sleep(0.2)

    def _poll(self) -> None:
        self._last_poll = time.monotonic()
        _LOGGER.debug("Polling-Zyklus")
        steps: list[Callable[[], bool]] = [
            self._step_battery,
            self._step_pv,
            self._step_es_status,
            self._step_es_mode,
        ]
        if self.s.enable_em:
            steps.append(self._step_em)

        ok = True
        for index, func in enumerate(steps):
            if not self._running:
                return
            if not func():
                ok = False
            if index < len(steps) - 1:
                self._sleep_with_commands(self.s.request_delay)
        if ok:
            self._set_communication(True)

    def _passive_keepalive(self) -> None:
        if not self._initialized:
            return
        ctrl = self.states[GRP_ENERGY_CONTROL]
        if ctrl.get("applied_mode") != MODE_PASSIVE:
            return
        # Bei aktiver Selbstregelung ist das Nachsenden zwingend, sonst laeuft
        # der Countdown des Geraets ab, sobald keine neuen Werte kommen.
        if not (self.s.passive_keepalive or self._regulation_active()):
            return
        cd = int(ctrl.get("passive_cd_time", self.s.passive_cd_time_default) or 0)
        if cd <= 0:
            return
        interval = max(1.0, cd / 2.0)
        if time.monotonic() - self._last_passive_push >= interval:
            _LOGGER.debug(
                "Passive-Keepalive: %s W erneut gesendet (cd_time=%ss)",
                self._effective_passive_power(),
                cd,
            )
            self._apply_mode(refresh=False)

    # =================================================================
    # Hilfsfunktionen
    # =================================================================
    def _query(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        with_instance: bool = True,
    ) -> dict[str, Any] | None:
        try:
            result = self.udp.request(method, params, with_instance=with_instance)
        except ApiError as err:
            _LOGGER.error("%s: %s", method, err)
            self.health.update(last_error=str(err))
            return None
        except UdpError as err:
            self._handle_udp_error(method, err)
            return None
        self._watchdog_failures = 0
        self.health.update(
            device_ok=True, watchdog_failures=0, last_success=_utcnow(), last_error=None
        )
        self.states[GRP_SYSTEM]["last_update"] = _utcnow()
        return result

    def _handle_udp_error(self, method: str, err: UdpError) -> None:
        self.health.update(last_error=f"{method}: {err}")
        if not err.trigger_watchdog:
            _LOGGER.warning(
                "%s verworfen (retries=0, kein Watchdog): %s", method, err
            )
            return
        self._watchdog_failures += 1
        _LOGGER.error(
            "\033[1;31mWatchdog ausgeloest\033[0m durch %s (%s) - Fehler %s/%s",
            method,
            err,
            self._watchdog_failures,
            self.s.watchdog_failure_threshold,
        )
        self._set_communication(False, str(err))
        self.health.update(watchdog_failures=self._watchdog_failures)
        if self._watchdog_failures >= self.s.watchdog_failure_threshold:
            first = self.health.snapshot().get("device_ok") is not False
            self.health.update(device_ok=False)
            self._initialized = False
            if first:
                _LOGGER.error(
                    "Health-Endpoint meldet unhealthy - Supervisor-Watchdog "
                    "startet das Add-on neu, sofern aktiviert"
                )

    def _set_communication(self, ok: bool, reason: str | None = None) -> None:
        state = COMM_OK if ok else COMM_FAIL
        if self.states[GRP_SYSTEM].get("communication") != state:
            if ok:
                _LOGGER.info("\033[1;32mCommunication established = ON\033[0m")
            else:
                _LOGGER.error(
                    "\033[1;31mCommunication established = FAIL\033[0m%s",
                    f" ({reason})" if reason else "",
                )
        self.states[GRP_SYSTEM]["communication"] = state
        self.states[GRP_SYSTEM]["comm_ok"] = ok
        if ok:
            self.health.update(device_ok=True)
        self._publish_state(GRP_SYSTEM)

    def _note_set_result(self, method: str, result: dict[str, Any]) -> None:
        value = result.get("set_result")
        text = f"{method}: {'OK' if value in (True, 'true', 'ture', 1) else value}"
        self.states[GRP_SYSTEM]["last_set_result"] = text
        _LOGGER.info("%s", text)

    def _control_entities(self) -> list[Ent]:
        return build_control_entities(
            self.s.passive_power_min,
            self.s.passive_power_max,
            self.s.passive_cd_time_max,
        )

    def _ensure_discovery_builder(self, version: Any = None) -> None:
        if self.disc is not None:
            return
        self.disc = DiscoveryBuilder(
            uid=self.s.uid(),
            base_topic=self.s.base_topic,
            discovery_prefix=self.s.mqtt_discovery_prefix,
            availability_topic=self.s.availability_topic,
            area=self.s.mqtt_suggested_area,
            model=self.s.device_type or "Marstek",
            sw_version=str(version or "unknown"),
        )

    def _publish_group(self, group: str, ents: list[Ent]) -> None:
        self._ensure_discovery_builder()
        if group not in self._discovered:
            assert self.disc is not None
            for ent in ents:
                topic, payload = self.disc.build(group, ent)
                self.mqtt.publish(topic, payload, retain=True, qos=1)
            self._discovered.add(group)
            _LOGGER.info(
                "Discovery veroeffentlicht: \033[1m%s\033[0m (%s Entities)",
                GROUP_TITLES[group],
                len(ents),
            )
        self._publish_state(group)

    def _publish_state(self, group: str) -> None:
        if self.disc is None:
            return
        payload = {k: v for k, v in self.states[group].items() if not k.startswith("_")}
        self.mqtt.publish(self.disc.state_topic(group), payload, retain=True)

    def _publish_all_states(self) -> None:
        for group in self._discovered:
            self._publish_state(group)

    # -- Schlafen mit Reaktionsfaehigkeit -------------------------------
    def _sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while self._running and time.monotonic() < end:
            time.sleep(min(0.2, max(0.0, end - time.monotonic())))

    def _sleep_with_commands(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while self._running and time.monotonic() < end:
            self._process_commands()
            time.sleep(min(0.1, max(0.0, end - time.monotonic())))


def _clean(result: dict[str, Any]) -> dict[str, Any]:
    """Interne Metafelder entfernen."""
    return {k: v for k, v in result.items() if not k.startswith("_")}
