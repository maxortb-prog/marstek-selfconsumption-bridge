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
    COMM_INIT,
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
from .logging_setup import CALC_LEVEL
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
        self._init_failures = 0
        self._last_query_timed_out = False
        self._discovered: set[str] = set()
        self._poll_last: dict[str, float] = {}
        self._last_write = 0.0
        self._last_passive_push = 0.0
        self._last_regulation_send = 0.0
        self._last_regulation_input: float | None = None
        # Zuletzt befohlene Aenderung, die sich in der Messung noch nicht
        # niedergeschlagen hat (Totzeit von Geraet und Sensor).
        self._unseen_delta = 0.0
        self._unseen_since = 0.0
        self._last_target_saturated = False
        self._last_in_band = False
        self._last_calc: dict[str, float] = {}
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
            min_gap=settings.request_delay,
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
        self._regulation_seed_pending = bool(settings.restore_state)
        if settings.restore_state:
            self._restore_control_state()

        self.states[GRP_SYSTEM].update(
            {
                "communication": COMM_INIT,
                "comm_ok": False,
                "dod_value": settings.dod_value,
                "ble_block": settings.ble_block_enable,
                "led_state": settings.led_state,
                "last_set_result": None,
                "last_update": None,
            }
        )

    # =================================================================
    # Zustand ueber Neustarts hinweg
    # =================================================================
    RESTORED_KEYS = (
        "passive_power",
        "passive_cd_time",
        "self_regulation",
        "target_mode",
        "regulation_output",
    )

    def _config_defaults(self) -> dict[str, Any]:
        """Die Startwerte aus der Add-on Konfiguration zu den Steuerwerten."""
        return {
            "passive_power": self.s.passive_power_default,
            "passive_cd_time": self.s.passive_cd_time_default,
            "self_regulation": self.s.self_regulation_enabled,
        }

    def _restore_control_state(self) -> None:
        """Steuerwerte aus dem State-File uebernehmen.

        Wiederhergestellt werden Deckel, Countdown, der Schalter der
        Selbstregelung, der vorgemerkte Modus und der zuletzt berechnete
        Sollwert. Bewusst *nicht* der zuletzt aktive Modus: ob das Geraet noch
        im Passive-Modus steht, weiss erst ES.GetMode.

        Wurde die zugehoerige Option in der Add-on Konfiguration seit dem
        Speichern geaendert, gewinnt die Konfiguration. Sonst waere eine
        Aenderung an ``passive_cd_time_default`` und Co. wirkungslos, weil der
        alte Laufzeitwert sie ueberschreibt.
        """
        state = load_state()
        saved = state.get("control")
        if not isinstance(saved, dict) or not saved:
            return
        previous = state.get("control_defaults")
        if not isinstance(previous, dict):
            previous = {}
        current = self._config_defaults()

        ctrl = self.states[GRP_ENERGY_CONTROL]
        taken: list[str] = []
        skipped: list[str] = []
        for key in self.RESTORED_KEYS:
            if key not in saved or saved[key] is None:
                continue
            # Kein Eintrag in previous (State-File aus einer aelteren Version)
            # zaehlt wie "geaendert" - so gewinnt die Konfiguration einmalig,
            # statt dass ein alter Laufzeitwert sie weiter ueberschreibt.
            if key in current and previous.get(key) != current[key]:
                skipped.append(f"{key}={current[key]}")
                continue
            ctrl[key] = saved[key]
            taken.append(f"{key}={saved[key]}")
        if taken:
            _LOGGER.info("Steuerzustand wiederhergestellt: %s", ", ".join(taken))
        if skipped:
            _LOGGER.info(
                "Aus der Konfiguration uebernommen (dort geaendert): %s",
                ", ".join(skipped),
            )

    def _save_control_state(self) -> None:
        if not self.s.restore_state:
            return
        ctrl = self.states[GRP_ENERGY_CONTROL]
        save_state(
            {
                "control": {k: ctrl.get(k) for k in self.RESTORED_KEYS},
                "control_defaults": self._config_defaults(),
            }
        )

    def _seed_regulation_from_device(self, data: dict[str, Any]) -> None:
        """Nach dem Start den Sollwert aus der Geraetemeldung uebernehmen.

        ``ongrid_power`` aus ``ES.GetMode`` ist die tatsaechliche Leistung des
        Geraets. Solange es noch ``Passive`` meldet, ist das die beste Auskunft
        darueber, wo die Regelung weitermachen sollte - danach ist der
        Countdown abgelaufen und der Wert nicht mehr aussagekraeftig, dann
        zaehlt der gesicherte Wert.
        """
        if not self._regulation_seed_pending:
            return
        self._regulation_seed_pending = False

        ctrl = self.states[GRP_ENERGY_CONTROL]
        cap = max(0, min(self.s.passive_power_max, int(ctrl.get("passive_power", 0))))
        mode = data.get("mode")
        power = data.get("ongrid_power")

        if mode == MODE_PASSIVE and isinstance(power, (int, float)) and power > 0:
            seed = int(max(0, min(cap, round(float(power)))))
            ctrl["regulation_output"] = seed
            _LOGGER.info(
                "Regelung setzt beim Geraetewert auf: \033[1m%s W\033[0m "
                "(ES.GetMode ongrid_power, Modus Passive, Deckel %s W)",
                seed,
                cap,
            )
        elif ctrl.get("regulation_output") is not None:
            seed = int(max(0, min(cap, int(ctrl["regulation_output"]))))
            ctrl["regulation_output"] = seed
            _LOGGER.info(
                "Geraet meldet Modus '%s' - Regelung setzt beim gesicherten "
                "Wert auf: \033[1m%s W\033[0m (Deckel %s W)",
                mode,
                seed,
                cap,
            )
        else:
            return
        self._publish_state(GRP_ENERGY_CONTROL)

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
            "Timing: delay=%ss timeout=%ss retries=%s max=%ss",
            self.s.request_delay,
            self.s.request_timeout,
            self.s.request_retries,
            self.s.request_max_time,
        )
        if self.s.poll_enabled:
            aktiv = [
                f"{name}={interval}s"
                for name, interval, _ in self._poll_jobs()
                if interval > 0
            ]
            _LOGGER.info(
                "Polling: %s", ", ".join(aktiv) if aktiv else "alle Intervalle auf 0"
            )
        else:
            _LOGGER.info("Polling deaktiviert - Abfragen nur ueber die Refresh-Buttons")

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

        if (
            self.s.self_regulation_enabled
            and 0 < self.s.self_regulation_min_interval < self.s.self_regulation_settle_time
        ):
            _LOGGER.warning(
                "self_regulation_settle_time (%.0fs) ist groesser als "
                "self_regulation_min_interval (%.0fs) - aufeinanderfolgende "
                "Kommandos ueberlagern sich in der Totzeit-Kompensation und der "
                "Regler korrigiert zu stark nach unten. Empfehlung: "
                "settle_time <= min_interval",
                self.s.self_regulation_settle_time,
                self.s.self_regulation_min_interval,
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
                # Ein Timeout heisst: das Geraet ist gerade nicht ansprechbar.
                # Weiterlaufen kostet nur Zeit, denn die restlichen Schritte
                # laufen genauso ins Leere. Also sofort abbrechen und warten,
                # bis das Geraet nach Ablauf seiner cd_time wieder da ist.
                if self._last_query_timed_out:
                    self._abort_initialization(label)
                    return
                ok = False
            if index < len(steps):
                self._sleep_with_commands(self.s.request_delay)

        if ok:
            self._initialized = True
            self._init_failures = 0
            self._reset_poll_timers()
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
                self._init_retry_delay(),
            )
            self._sleep_with_commands(self._init_retry_delay())

    def _init_retry_delay(self) -> float:
        """Wartezeit bis zum naechsten Init-Versuch: die doppelte cd_time.

        Der Speicher schliesst den UDP-Port, wenn im Passive-Modus keine
        Kommandos mehr kommen, und meldet sich erst nach Ablauf seines
        Countdowns zurueck. Doppelt gewaehlt, damit der Versuch sicher in das
        Zeitfenster danach faellt.
        """
        cd = self.states[GRP_ENERGY_CONTROL].get("passive_cd_time")
        if not isinstance(cd, (int, float)) or cd <= 0:
            cd = self.s.passive_cd_time_default
        return max(2.0, float(cd) * 2.0)

    def _abort_initialization(self, label: str) -> None:
        """Init nach einem Timeout abbrechen und auf das Geraet warten."""
        self._init_failures += 1
        wait = self._init_retry_delay()
        threshold = self.s.watchdog_failure_threshold

        if self._init_failures >= threshold:
            self._set_communication_state(
                COMM_FAIL, f"{self._init_failures} Init-Versuche gescheitert"
            )
            self.health.update(device_ok=False, watchdog_failures=self._init_failures)
            _LOGGER.error(
                "Initialisierung bei %s abgebrochen (Timeout) - Versuch %s/%s "
                "gescheitert. Health-Endpoint meldet unhealthy, der "
                "Supervisor-Watchdog startet das Add-on neu. Naechster Versuch "
                "in %.0fs",
                label,
                self._init_failures,
                threshold,
                wait,
            )
        else:
            self._set_communication_state(COMM_INIT, f"Timeout bei {label}")
            _LOGGER.warning(
                "Initialisierung bei %s abgebrochen (Timeout) - das Geraet ist "
                "nicht ansprechbar. Neuer Versuch in %.0fs (Versuch %s/%s)",
                label,
                wait,
                self._init_failures,
                threshold,
            )
        self._sleep_with_commands(wait)

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
            _LOGGER.log(
                CALC_LEVEL, "PV-Energie: kein gueltiger pv_power-Wert (%r)", power
            )
            return

        now = time.monotonic()
        power = float(power)
        previous = self._pv_last_sample
        self._pv_last_sample = (now, power)
        self.states[GRP_ENERGY_STATUS]["calc_pv_energy"] = round(self._pv_energy_wh, 2)

        if previous is None:
            _LOGGER.log(
                CALC_LEVEL,
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
        _LOGGER.log(
            CALC_LEVEL,
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

        self._seed_regulation_from_device(clean)

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
        self._note_write()
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
        self._note_write()
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
        self._note_write()
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

    def _handle_apply_request(self) -> None:
        """Druck auf *Apply mode*.

        Laeuft der Passive-Modus bereits und ist die Selbstregelung aktiv, wird
        **nicht** gesendet: Zeitpunkt und Leistung bestimmt dann die interne
        Regelschleife samt Keepalive. Ein Apply von aussen wuerde den zuletzt
        berechneten - womoeglich schon veralteten - Sollwert dazwischenschieben
        und mit dem naechsten Regelkommando kollidieren.

        Fuer einen echten Moduswechsel bleibt der Button unveraendert wirksam.
        """
        ctrl = self.states[GRP_ENERGY_CONTROL]
        target = ctrl.get("target_mode")
        if (
            self._regulation_active()
            and target == MODE_PASSIVE
            and ctrl.get("applied_mode") == MODE_PASSIVE
        ):
            _LOGGER.info(
                "Apply ignoriert - Passive laeuft bereits, die Selbstregelung "
                "bestimmt Zeitpunkt und Leistung selbst"
            )
            if ctrl.get("regulation_input") is not None:
                self._pending_regulation = float(ctrl["regulation_input"])
            return
        self._apply_mode()

    def _apply_mode(self, refresh: bool = True) -> bool:
        """Den vorgemerkten Modus an das Geraet senden.

        ``refresh=False`` laesst das anschliessende ES.GetMode weg - das nutzt
        die Selbstregelung, damit pro Regelschritt nur ein Kommando laeuft.
        Mit ``refresh=True`` wird nur nachgelesen, wenn ``poll_interval_mode``
        groesser 0 ist.
        """
        mode = str(self.states[GRP_ENERGY_CONTROL].get("target_mode") or MODE_AUTO)
        try:
            config = self._build_mode_config(mode)
        except ValueError as err:
            _LOGGER.error("%s", err)
            return False

        # Vom Benutzer ausgeloest -> INFO, aus Regelung/Keepalive -> DEBUG,
        # damit die INFO-Ebene bei aktiver Selbstregelung lesbar bleibt.
        _LOGGER.log(
            logging.INFO if refresh else CALC_LEVEL,
            "\033[1;36mES.SetMode -> %s\033[0m %s",
            mode,
            config,
        )
        result = self._query(M_ES_SET_MODE, {"config": config})
        if result is None:
            return False
        self._note_write()
        self.states[GRP_ENERGY_CONTROL]["applied_mode"] = mode
        self._note_set_result(
            M_ES_SET_MODE, result, logging.INFO if refresh else CALC_LEVEL
        )
        self._publish_state(GRP_ENERGY_CONTROL)
        self._last_passive_push = time.monotonic()
        # Nach einem manuellen Moduswechsel den neuen Zustand nachlesen, damit
        # die Gruppe *Marstek Energy Mode* stimmt. Steht poll_interval_mode auf
        # 0, will der Benutzer diese Gruppe gar nicht aktuell halten - dann
        # entfaellt auch dieser Zusatzaufruf. Wichtig, weil eine Automation, die
        # zyklisch auf "Apply mode" drueckt, sonst dauernd ES.GetMode ausloest.
        if refresh and self.s.poll_interval_mode > 0:
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
            # Der Deckel kann sich zwischen zwei Regelwerten geaendert haben
            # (z. B. SOC-abhaengig aus Home Assistant). Auch der Keepalive darf
            # dann nicht mehr den alten, hoeheren Sollwert weitersenden.
            cap = max(0, min(self.s.passive_power_max, int(ctrl.get("passive_power", 0))))
            capped = int(max(0, min(cap, int(value))))
            if capped != int(value):
                _LOGGER.log(
                    CALC_LEVEL,
                    "Sollwert %s W auf den aktuellen Deckel %s W begrenzt",
                    int(value),
                    cap,
                )
                ctrl["regulation_output"] = capped
            return capped
        power = int(ctrl.get("passive_power", 0))
        return max(self.s.passive_power_min, min(self.s.passive_power_max, power))

    def _on_cap_changed(self) -> None:
        """Reaktion auf eine geaenderte Obergrenze (*Passive power*).

        Wird der Deckel gesenkt - etwa weil der SOC unter eine Schwelle faellt -
        muss der Sollwert sofort mitgehen. Sonst schickt der Keepalive bis zu
        ``cd_time`` Sekunden lang weiter die alte, zu hohe Leistung. Ein
        Absenken ist immer sicher und wird deshalb ohne Ruecksicht auf Totband
        und Mindestabstand gesendet. Wird der Deckel angehoben, uebernimmt das
        der naechste regulaere Regelschritt.
        """
        if not self._regulation_active():
            return
        ctrl = self.states[GRP_ENERGY_CONTROL]
        if ctrl.get("applied_mode") != MODE_PASSIVE:
            return
        current = ctrl.get("regulation_output")
        if current is None:
            return

        cap = max(0, min(self.s.passive_power_max, int(ctrl.get("passive_power", 0))))
        if int(current) <= cap:
            # Deckel angehoben oder unveraendert: den zuletzt empfangenen Wert
            # erneut einplanen, damit der naechste Schritt den neuen Spielraum
            # nutzt.
            if ctrl.get("regulation_input") is not None:
                self._pending_regulation = float(ctrl["regulation_input"])
            return

        _LOGGER.info(
            "Deckel auf %s W gesenkt - Sollwert sofort von %s W auf "
            "\033[1m%s W\033[0m begrenzt",
            cap,
            int(current),
            cap,
        )
        ctrl["regulation_output"] = cap
        self._pending_regulation = None
        self._publish_state(GRP_ENERGY_CONTROL)
        if self._apply_mode(refresh=False):
            self._last_regulation_send = time.monotonic()
            self._note_commanded_change(float(cap - int(current)))

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

        # Jede empfangene Nachricht wird mit dem daraus berechneten Sollwert
        # protokolliert - auch dann, wenn sie anschliessend nicht gesendet wird.
        if not self._regulation_active():
            _LOGGER.info(
                "MQTT-Regelwert \033[1m%.1f W\033[0m - Selbstregelung ist aus",
                value,
            )
            return
        if ctrl.get("applied_mode") != MODE_PASSIVE:
            _LOGGER.info(
                "MQTT-Regelwert \033[1m%.1f W\033[0m - Passive-Modus ist nicht "
                "aktiv, kein Kommando",
                value,
            )
            return

        current = ctrl.get("regulation_output")
        target = self._compute_regulation_output(value)
        _LOGGER.info(
            "MQTT-Regelwert \033[1m%.1f W\033[0m (Halteband %s-%s W) | Sollwert "
            "%s W -> \033[1m%s W\033[0m | Deckel %s W%s",
            value,
            self.s.self_regulation_band_low,
            self.s.self_regulation_reserve,
            current if current is not None else 0,
            target,
            max(0, int(ctrl.get("passive_power", 0))),
            " | im Halteband, keine Korrektur" if self._last_in_band else "",
        )
        self._log_calculation()
        self._pending_regulation = value
        self._flush_regulation()

    def _log_calculation(self) -> None:
        """Den Rechenweg eines Regelschritts nachvollziehbar machen."""
        c = self._last_calc
        if not c or not _LOGGER.isEnabledFor(CALC_LEVEL):
            return
        if self._last_in_band:
            grund = "im Halteband"
        elif self._last_target_saturated:
            grund = "am Anschlag begrenzt"
        elif c["error"] > 0:
            grund = (
                f"hoch, gain {self.s.self_regulation_step_gain} / "
                f"max {self.s.self_regulation_step_up} W"
            )
        else:
            grund = "runter, voller Betrag"
        _LOGGER.log(
            CALC_LEVEL,
            "Rechnung: Netz %.1f W - Totzeit %.1f W = %.1f W | Band %s-%s W | "
            "Abweichung %+.1f W | Schritt %+.1f W (%s) | %s -> %s W | Deckel %s W",
            c["value"],
            c["unseen"],
            c["measured"],
            self.s.self_regulation_band_low,
            self.s.self_regulation_reserve,
            c["error"],
            c["step"],
            grund,
            c["base"],
            c["out"],
            c["cap"],
        )

    def _unseen_effect(self) -> float:
        """Noch nicht sichtbarer Anteil der zuletzt befohlenen Aenderung.

        Zwischen Kommando und Messwert liegt eine Totzeit: das Geraet braucht
        einen Moment, und der gemittelte Sensor noch laenger. Ohne Korrektur
        wuerde der Regler denselben Fehler mehrfach ausregeln und dabei massiv
        ueberschiessen. Der Anteil verfaellt linear ueber
        ``self_regulation_settle_time``.
        """
        settle = self.s.self_regulation_settle_time
        if settle <= 0 or self._unseen_delta == 0.0:
            return 0.0
        age = time.monotonic() - self._unseen_since
        if age >= settle:
            self._unseen_delta = 0.0
            return 0.0
        return self._unseen_delta * (1.0 - age / settle)

    def _note_commanded_change(self, delta: float) -> None:
        """Eine gerade gesendete Sollwertaenderung als 'noch unsichtbar' merken."""
        if self.s.self_regulation_settle_time <= 0:
            return
        # Ein noch offener Rest wird mitgenommen, falls zwei Kommandos kurz
        # hintereinander gehen.
        self._unseen_delta = self._unseen_effect() + delta
        self._unseen_since = time.monotonic()

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

        Zwischen ``self_regulation_band_low`` und ``self_regulation_reserve``
        liegt ein Halteband, in dem gar nicht geregelt wird: ein Netzbezug
        unterhalb der Reserve ist besser als die Reserve selbst und kein Grund,
        Speicherleistung zurueckzunehmen.

        Vom Fehler wird ausserdem der Teil der zuletzt befohlenen Aenderung
        abgezogen, der sich in der Messung noch nicht zeigen kann - siehe
        ``_unseen_effect``.
        """
        ctrl = self.states[GRP_ENERGY_CONTROL]
        cap = max(0, min(self.s.passive_power_max, int(ctrl.get("passive_power", 0))))
        base = int(ctrl.get("regulation_output") or 0)

        # Um die Totzeit bereinigter Messwert.
        measured = value - self._unseen_effect()
        reserve = self.s.self_regulation_reserve
        low = self.s.self_regulation_band_low

        # Halteband: zwischen band_low und der Reserve ist alles in Ordnung -
        # ein kleinerer Netzbezug als die Reserve ist besser als die Reserve
        # selbst, dafuer wird nicht gegengeregelt. Ausserhalb des Bands wird in
        # beide Richtungen auf die Reserve zurueckgeregelt.
        if measured > reserve:
            error = measured - reserve
        elif measured < low:
            error = measured - reserve
        else:
            error = 0.0
        self._last_in_band = error == 0.0

        if error > 0:
            step = min(error * self.s.self_regulation_step_gain,
                       float(self.s.self_regulation_step_up))
        else:
            step = error
            if self.s.self_regulation_step_down > 0:
                step = max(step, -float(self.s.self_regulation_step_down))

        raw = base + step
        out = int(max(0, min(cap, round(raw))))
        self._last_calc = {
            "value": value,
            "unseen": value - measured,
            "measured": measured,
            "error": error,
            "step": step,
            "base": base,
            "cap": cap,
            "out": out,
        }
        # Begrenzt? Dann steht der Regler am Anschlag und das Totband darf den
        # letzten Schritt dorthin nicht blockieren.
        self._last_target_saturated = raw > cap or raw < 0
        return out

    def _flush_regulation(self) -> None:
        """Ausstehenden Regelwert senden.

        Ein Schritt nach unten darf Totband und Mindestabstand ueberspringen
        (``self_regulation_fast_down``), damit auf einen plotzlichen Lastabfall
        sofort reagiert wird. Nach oben bleiben beide Bremsen aktiv.

        Das Totband bezieht sich auf die Abweichung des Netzwerts. Aendert sich
        der Sollwert trotz ausreichender Abweichung nicht - etwa weil er schon
        am Deckel steht - wird ebenfalls nicht gesendet.
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

        # Auch ein Fast-Down haelt einen (kuerzeren) Mindestabstand ein. Ohne
        # ihn wuerde jede eingehende Nachricht einen weiteren Schritt ausloesen,
        # bevor die vorige Korrektur ueberhaupt messbar ist.
        since_send = time.monotonic() - self._last_regulation_send
        if fast:
            if since_send < self.s.self_regulation_min_interval_down:
                return  # Wert bleibt vorgemerkt
        else:
            if since_send < self.s.self_regulation_min_interval:
                return  # Wert bleibt vorgemerkt und wird spaeter gesendet
            # Das Totband gilt fuer die Abweichung des Netzwerts, nicht fuer
            # den berechneten Sollwert. Sonst haengt seine Wirkung an der
            # Verstaerkung: bei gain 0.5 entspraeche ein Totband von 5 W am
            # Ausgang einer Abweichung von 10 W am Eingang.
            error = float(self._last_calc.get("error", 0.0))
            if abs(error) < self.s.self_regulation_deadband:
                self._pending_regulation = None
                _LOGGER.log(
                    CALC_LEVEL,
                    "Abweichung %+.1f W liegt innerhalb des Totbands (%s W) - "
                    "kein Kommando",
                    error,
                    self.s.self_regulation_deadband,
                )
                return

        if last is not None and out == int(last):
            self._pending_regulation = None
            _LOGGER.log(
                CALC_LEVEL,
                "Sollwert bleibt bei %s W - kein Kommando noetig",
                out,
            )
            return

        self._pending_regulation = None
        ctrl["regulation_output"] = out
        _LOGGER.log(
            CALC_LEVEL,
            "Selbstregelung %s: %s W -> %s W wird gesendet%s",
            "RUNTER" if going_down else "hoch",
            last if last is not None else 0,
            out,
            " (Fast-Down, Totband/Takt uebersprungen)" if fast
            else (" (Anschlag, Totband uebersprungen)"
                  if self._last_target_saturated else ""),
        )
        self._publish_state(GRP_ENERGY_CONTROL)
        if self._apply_mode(refresh=False):
            self._last_regulation_send = time.monotonic()
            self._note_commanded_change(float(out - (last if last is not None else 0)))
        else:
            # Das Kommando ist nicht angekommen - der Speicher laeuft weiter
            # mit dem alten Sollwert. Den internen Stand zurueckdrehen, sonst
            # rechnet der naechste Schritt von einem Wert aus, den das Geraet
            # nie bekommen hat.
            _LOGGER.warning(
                "Sollwert %s W konnte nicht gesendet werden - zurueck auf %s W, "
                "neuer Versuch beim naechsten Durchlauf",
                out,
                last if last is not None else 0,
            )
            ctrl["regulation_output"] = last
            self._pending_regulation = value
            self._publish_state(GRP_ENERGY_CONTROL)

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
        previous = int(current)
        ctrl["regulation_output"] = 0
        self._pending_regulation = None
        self._publish_state(GRP_ENERGY_CONTROL)
        if self._apply_mode(refresh=False):
            self._last_regulation_send = time.monotonic()
            self._note_commanded_change(float(-previous))

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
            if ctrl.get("target_mode") != value:
                _LOGGER.info(
                    "Zielmodus '%s' vorgemerkt - mit 'Apply mode' aktivieren", value
                )
            ctrl["target_mode"] = value
            self._publish_state(GRP_ENERGY_CONTROL)
        elif suffix == f"{GRP_ENERGY_CONTROL}/passive_power/set":
            value = int(float(payload))
            ctrl["passive_power"] = max(
                self.s.passive_power_min, min(self.s.passive_power_max, value)
            )
            self._publish_state(GRP_ENERGY_CONTROL)
            self._on_cap_changed()
        elif suffix == f"{GRP_ENERGY_CONTROL}/passive_cd_time/set":
            value = int(float(payload))
            ctrl["passive_cd_time"] = max(
                0, min(self.s.passive_cd_time_max, value)
            )
            self._publish_state(GRP_ENERGY_CONTROL)
        elif suffix == f"{GRP_ENERGY_CONTROL}/self_regulation/set":
            self._set_self_regulation(payload.strip().upper() == "ON")
        elif suffix == f"{GRP_ENERGY_CONTROL}/apply/set":
            self._handle_apply_request()
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
        self._wait_for_write_quiet()
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

        self._run_due_polls()

        self._flush_regulation()
        self._check_regulation_timeout()
        self._passive_keepalive()
        self._sleep(0.2)

    def _poll_jobs(self) -> list[tuple[str, int, Callable[[], bool]]]:
        """Die einzeln taktbaren Abfragen samt ihrem Intervall.

        Jede Abfrage hat ihr eigenes Intervall in Sekunden, ``0`` schaltet sie
        ab. Das ist noetig, weil die Abfragen sehr unterschiedlich interessant
        sind: ES.GetStatus liefert die laufenden Leistungswerte, Bat.GetStatus
        vor allem die Temperatur, ES.GetMode ist nach dem Start meist statisch
        und PV.GetStatus steckt in Teilen schon in ES.GetStatus.
        """
        return [
            ("es_status", self.s.poll_interval_es_status, self._step_es_status),
            ("battery", self.s.poll_interval_battery, self._step_battery),
            ("pv", self.s.poll_interval_pv, self._step_pv),
            ("mode", self.s.poll_interval_mode, self._step_es_mode),
            ("em", self.s.poll_interval_em, self._step_em),
        ]

    def _reset_poll_timers(self) -> None:
        """Nach der Init laufen alle Intervalle neu an."""
        now = time.monotonic()
        self._poll_last = {name: now for name, _, _ in self._poll_jobs()}

    def _run_due_polls(self) -> None:
        """Faellige Abfragen ausfuehren - hoechstens eine pro Durchlauf.

        Der Rest kommt im naechsten Schleifendurchlauf (alle 0,2 s). So drueckt
        ein gemeinsamer Faelligkeitszeitpunkt nicht mehrere Anfragen auf einmal
        heraus; die Mindestpause des UDP-Clients haelt zusaetzlich Abstand zu
        Regelkommandos und Keepalive.
        """
        if not self._initialized or not self.s.poll_enabled:
            return
        now = time.monotonic()
        for name, interval, func in self._poll_jobs():
            if interval <= 0:
                continue
            last = self._poll_last.get(name, 0.0)
            if now - last < interval:
                continue
            # Direkt nach einem Schreibkommando ist der Speicher beschaeftigt.
            # Die Abfrage wird verschoben - aber nur so lange, bis sie das
            # Doppelte ihres Intervalls ueberfaellig ist, damit sie bei dichtem
            # Regeltakt nicht dauerhaft verhungert.
            remaining = self._write_quiet_remaining()
            if remaining > 0 and now - last < interval * 2:
                _LOGGER.log(
                    CALC_LEVEL,
                    "Abfrage %s verschoben, noch %.1fs Ruhezeit nach dem "
                    "letzten Schreibkommando",
                    name,
                    remaining,
                )
                return

            self._poll_last[name] = now
            _LOGGER.debug("Polling faellig: %s (alle %ss)", name, interval)
            if func():
                self._set_communication(True)
            return

    def _poll(self) -> None:
        """Alle Abfragen einmal ausfuehren (Button *Refresh data*)."""
        _LOGGER.debug("Vollstaendige Abfrage aller Gruppen")
        self._wait_for_write_quiet()
        steps: list[Callable[[], bool]] = [
            self._step_battery,
            self._step_pv,
            self._step_es_status,
            self._step_es_mode,
        ]
        if self.s.enable_em:
            steps.append(self._step_em)

        ok = True
        now = time.monotonic()
        for index, func in enumerate(steps):
            if not self._running:
                return
            if not func():
                ok = False
            if index < len(steps) - 1:
                self._sleep_with_commands(self.s.request_delay)
        self._poll_last = {name: now for name, _, _ in self._poll_jobs()}
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
            _LOGGER.log(
                CALC_LEVEL,
                "Passive-Keepalive: %s W erneut gesendet (cd_time=%ss)",
                self._effective_passive_power(),
                cd,
            )
            self._apply_mode(refresh=False)

    # =================================================================
    # Hilfsfunktionen
    # =================================================================
    def _note_write(self) -> None:
        """Zeitpunkt des letzten Schreibkommandos merken.

        Direkt nach einem ES.SetMode (und den uebrigen Set-Befehlen) ist der
        Speicher ein paar Sekunden beschaeftigt und laesst Statusabfragen ins
        Leere laufen. Waehrend dieser Ruhezeit wird nicht abgefragt.
        """
        self._last_write = time.monotonic()

    def _write_quiet_remaining(self) -> float:
        quiet = self.s.poll_quiet_after_write
        if quiet <= 0 or self._last_write <= 0:
            return 0.0
        return max(0.0, quiet - (time.monotonic() - self._last_write))

    def _wait_for_write_quiet(self) -> None:
        """Vor einer angeforderten Abfrage die Ruhezeit abwarten."""
        remaining = self._write_quiet_remaining()
        if remaining > 0:
            _LOGGER.log(
                CALC_LEVEL,
                "Warte %.1fs Ruhezeit nach dem letzten Schreibkommando",
                remaining,
            )
            self._sleep_with_commands(remaining)

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
            # Das Geraet hat geantwortet, nur inhaltlich ablehnend - das ist
            # kein Grund, die Init-Sequenz abzubrechen.
            self._last_query_timed_out = False
            _LOGGER.error("%s: %s", method, err)
            self.health.update(last_error=str(err))
            return None
        except UdpError as err:
            self._handle_udp_error(method, err)
            return None
        self._watchdog_failures = 0
        self._init_failures = 0
        self._last_query_timed_out = False
        self.health.update(
            device_ok=True, watchdog_failures=0, last_success=_utcnow(), last_error=None
        )
        self.states[GRP_SYSTEM]["last_update"] = _utcnow()
        return result

    def _handle_udp_error(self, method: str, err: UdpError) -> None:
        self._last_query_timed_out = True
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
        self._set_communication_state(COMM_OK if ok else COMM_FAIL, reason)

    def _set_communication_state(self, state: str, reason: str | None = None) -> None:
        """Zustand der Entity *Communication established* setzen.

        ``ON``   - Gespraech mit dem Geraet laeuft.
        ``INIT`` - Bridge startet bzw. wartet darauf, dass das Geraet
                   wieder ansprechbar wird.
        ``FAIL`` - Geraet antwortet nicht mehr, der Watchdog hat ausgeloest.
        """
        if self.states[GRP_SYSTEM].get("communication") != state:
            if state == COMM_OK:
                _LOGGER.info("\033[1;32mCommunication established = ON\033[0m")
            elif state == COMM_INIT:
                _LOGGER.warning(
                    "\033[1;33mCommunication established = INIT\033[0m%s",
                    f" ({reason})" if reason else "",
                )
            else:
                _LOGGER.error(
                    "\033[1;31mCommunication established = FAIL\033[0m%s",
                    f" ({reason})" if reason else "",
                )
        self.states[GRP_SYSTEM]["communication"] = state
        self.states[GRP_SYSTEM]["comm_ok"] = state == COMM_OK
        if state == COMM_OK:
            self.health.update(device_ok=True)
        self._publish_state(GRP_SYSTEM)

    def _note_set_result(
        self, method: str, result: dict[str, Any], level: int = logging.INFO
    ) -> None:
        value = result.get("set_result")
        text = f"{method}: {'OK' if value in (True, 'true', 'ture', 1) else value}"
        self.states[GRP_SYSTEM]["last_set_result"] = text
        _LOGGER.log(level, "%s", text)

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
        if group == GRP_ENERGY_CONTROL:
            self._save_control_state()
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
