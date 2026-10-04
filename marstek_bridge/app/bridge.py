"""Kernlogik der Marstek MQTT - UDP Bridge."""

from __future__ import annotations

import json
import logging
import queue
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from datetime import time as dt_time
from typing import Any

from . import __project__, __version__
from .const import (
    CHARGE_INTENDED,
    CHARGE_OFF,
    CHARGE_UNEXPECTED,
    COMM_FAIL,
    COMM_INIT,
    COMM_OK,
    GROUP_TITLES,
    GRP_BATTERY,
    GRP_ENERGY_CONTROL,
    GRP_ENERGY_METER,
    GRP_ENERGY_MODE,
    GRP_ENERGY_PLAN,
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
    PLAN_LIMIT,
    PLAN_NO_DATA,
    PLAN_OK,
    PLAN_PV,
    SELECTABLE_MODES,
    SIGNAL_OK,
    SIGNAL_STUCK,
)
from .entities import (
    BATTERY_ENTITIES,
    ENERGY_METER_ENTITIES,
    ENERGY_MODE_ENTITIES,
    ENERGY_STATUS_ENTITIES,
    PLAN_ENTITIES,
    SYSTEM_ENTITIES,
    DiscoveryBuilder,
    Ent,
    build_control_entities,
    build_pv_entities,
)
from .health import HealthState
from .logging_setup import CALC_LEVEL, PLAN_LEVEL
from .mqtt_bridge import MqttBridge
from .settings import Settings, load_state, save_state
from .udp_client import ApiError, MarstekUdpClient, UdpError

_LOGGER = logging.getLogger("marstek.bridge")

# Wiederkehrende Meldungen ohne Konsequenz hoechstens alle X Sekunden.
QUIET_LOG_INTERVAL = 10.0

# So lange gilt die PV nach dem letzten nennenswerten Messwert als aktiv.
PV_HOLD_SECONDS = 600.0


def _parse_clock(wert: str) -> dt_time | None:
    """"hh:mm" in eine Uhrzeit umwandeln, None bei unbrauchbarer Eingabe."""
    try:
        stunde, minute = (int(x) for x in str(wert).split(":", 1))
        return dt_time(hour=stunde, minute=minute)
    except (ValueError, AttributeError):
        return None


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
        self._last_regulation_input: float | None = None
        self._last_target_saturated = False
        self._last_floor_applied = False
        self._last_in_band = False
        self._last_calc: dict[str, float] = {}
        # Messwerte mit Zeitstempel fuer das Mittelungsfenster.
        self._input_samples: list[tuple[float, float]] = []
        # Mittel und befohlene Aenderung des letzten Takts - daraus erkennt die
        # Bridge, ob der Sensor ueberhaupt noch reagiert.
        self._cycle_mean: float | None = None
        self._cycle_delta = 0
        self._jitter_sign = 1
        # Zuletzt gemeldete Ausgangsleistung mit Zeitstempel.
        self._last_ongrid: tuple[float, float] | None = None
        # Gelernter Verlust zwischen Vorgabe und gemeldeter Ausgangsleistung.
        self._loss_offset: float | None = None
        # Geglaettete Last fuer die Flugbahn und Tagesbuchhaltung der Prognose.
        self._load_samples: list[tuple[float, float]] = []
        self._forecast_today: float | None = None
        self._pv_day_start: float | None = None
        self._plan_day: str | None = None
        self._plan_saved = 0.0
        self._timing_warned = 0.0
        # Verdacht auf eine Leistungsreduktion, der noch bestaetigt werden muss.
        self._output_suspect: dict[str, float] | None = None
        # Wann zuletzt nennenswerte PV-Leistung gemeldet wurde.
        self._pv_last_seen: float | None = None
        # Nach einem Fehlschlag die Vorab-Abfrage einmal ueberspringen.
        self._skip_query_once = False
        # Einspeise-Korrektur hoechstens einmal je Takt.
        self._export_done = False
        self._reaction_failures = 0
        self._stuck_value: float | None = None
        # Solange gesetzt, bleibt "Communication established" auf FAIL.
        self._regulation_fault: str | None = None
        self._last_quiet_log = 0.0
        self._last_input_log = 0.0
        # Eigener PV-Energiezaehler: Summe in Wh plus letzte Stuetzstelle
        # (Zeitpunkt, Leistung) fuer die Trapezintegration.
        self._pv_energy_wh = float(load_state().get("pv_energy_wh") or 0.0)
        self._pv_last_sample: tuple[float, float] | None = None

        self.states: dict[str, dict[str, Any]] = {
            GRP_SYSTEM: {"request_failures": 0},
            GRP_BATTERY: {},
            GRP_PV: {},
            GRP_ENERGY_STATUS: {},
            GRP_ENERGY_MODE: {},
            GRP_ENERGY_CONTROL: {"regulation_signal": SIGNAL_OK},
            GRP_ENERGY_METER: {},
            GRP_ENERGY_PLAN: {},
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
            self._restore_plan_state()

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

    PLAN_KEYS = ("base_load", "forecast_factor", "output_dropouts", "output_glitches")

    def _restore_plan_state(self) -> None:
        """Gelernte Werte uebernehmen.

        Grundlast und Prognose-Faktor brauchen Naechte beziehungsweise Tage,
        bis sie stehen - die nach jedem Neustart neu zu lernen waere unnoetig.
        Der Verlust-Offset ist schneller wieder da, kostet aber auch nichts.
        """
        gespeichert = load_state().get("plan")
        if not isinstance(gespeichert, dict):
            return
        plan = self.states[GRP_ENERGY_PLAN]
        uebernommen: list[str] = []
        for key in self.PLAN_KEYS:
            if gespeichert.get(key) is not None:
                plan[key] = gespeichert[key]
                uebernommen.append(f"{key}={gespeichert[key]}")
        if gespeichert.get("loss_offset") is not None:
            self._loss_offset = float(gespeichert["loss_offset"])
            uebernommen.append(f"loss_offset={self._loss_offset:.1f}")
        for feld in ("forecast_today", "pv_day_start", "plan_day"):
            if gespeichert.get(feld) is not None:
                setattr(self, f"_{feld}", gespeichert[feld])
        if uebernommen:
            _LOGGER.info("Planungsdaten wiederhergestellt: %s", ", ".join(uebernommen))

    def _save_plan_state(self, sofort: bool = False) -> None:
        """Gelernte Werte sichern, hoechstens alle fuenf Minuten."""
        if not self.s.restore_state:
            return
        if not sofort and time.monotonic() - self._plan_saved < 300:
            return
        self._plan_saved = time.monotonic()
        plan = self.states[GRP_ENERGY_PLAN]
        save_state(
            {
                "plan": {
                    **{k: plan.get(k) for k in self.PLAN_KEYS},
                    "loss_offset": self._loss_offset,
                    "forecast_today": self._forecast_today,
                    "pv_day_start": self._pv_day_start,
                    "plan_day": self._plan_day,
                }
            }
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
                "Selbstregelung aktiv - Topic '%s', Halteband %s-%s W, "
                "Korrektur %.0f%% je Takt, Mittel ueber %.0fs, "
                "Einspeise-Reserve %.0f%%",
                self.regulation_topic,
                self.s.self_regulation_band_low,
                self.s.self_regulation_reserve,
                self.s.self_regulation_gain * 100,
                self.s.self_regulation_average_window,
                self.s.self_regulation_export_margin,
            )

        if self.s.self_regulation_enabled:
            takt = self.s.passive_keepalive_interval or (
                self.s.passive_cd_time_default / 2.0
            )
            empfohlen = round(min(0.9, max(0.1, takt / 20.0)), 2)
            if self.s.self_regulation_gain > empfohlen + 0.05:
                _LOGGER.warning(
                    "self_regulation_gain (%.2f) passt nicht zum Regeltakt von "
                    "%.0fs: das Geraet braucht rund 20s bis zum Einschwingen, "
                    "es wird also mehrfach auf denselben Fehler korrigiert. "
                    "Empfehlung fuer diesen Takt: %.2f oder kleiner",
                    self.s.self_regulation_gain,
                    takt,
                    empfohlen,
                )

        self._check_cycle_timing("beim Start")

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
            self.forecast_topic,
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
        _LOGGER.log(
            CALC_LEVEL,
            "Geraet meldet: Netz %s W | Batterie %s W | PV %s W | SOC %s %% | "
            "Insel %s W",
            clean.get("ongrid_power"),
            clean.get("bat_power"),
            clean.get("pv_power"),
            clean.get("bat_soc"),
            clean.get("offgrid_power"),
        )
        ongrid = clean.get("ongrid_power")
        if isinstance(ongrid, (int, float)) and not isinstance(ongrid, bool):
            self._last_ongrid = (float(ongrid), time.monotonic())
        self._update_pv_energy(clean.get("pv_power"))
        pv = clean.get("pv_power")
        if isinstance(pv, (int, float)) and pv >= self.s.plan_pv_min_power:
            self._pv_last_seen = time.monotonic()
        self._check_grid_charging()
        self._update_plan()
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

    def _with_jitter(self, power: int) -> int:
        """Den gesendeten Wert abwechselnd minimal anheben und absenken.

        Das Geraet ueberwacht offenbar selbst, ob sich am Eingang etwas tut,
        und faehrt die Leistung nach ein bis zwei Minuten ohne erkennbare
        Aenderung auf 0 zurueck. Bei konstanter Grundlast - niemand zuhause,
        50 W Dauerverbrauch - passiert genau das. Ein Wechsel um wenige Watt
        haelt die Erkennung wach.

        Betroffen ist nur der gesendete Wert. Der interne Sollwert und damit
        die gesamte Regelrechnung bleiben unberuehrt; im Mittelungsfenster
        hebt sich der Wechsel ohnehin auf.
        """
        jitter = self.s.passive_jitter
        if jitter <= 0 or power <= 0:
            return power
        # Am Deckel bringt der Wechsel nichts: Dort liegt die Last ueber dem,
        # was der Speicher liefern darf, der Eingang schwankt also ohnehin
        # kraeftig und das Geraet sieht genug Bewegung. Die Anhebung wuerde
        # zudem am Deckel abgeschnitten und nur nach unten wirken.
        cap = self._current_cap()
        if power >= cap:
            return power
        self._jitter_sign = -self._jitter_sign
        return int(max(0, min(cap, power + jitter * self._jitter_sign)))

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
                    "power": self._with_jitter(self._effective_passive_power()),
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
            return
        if self._apply_mode() and target == MODE_PASSIVE and self._regulation_active():
            # Auch ein Moduswechsel nach Passive ist eine Sollwertaenderung: das
            # Geraet schwingt danach ein. Ohne diesen Marker wuerde die Regelung
            # sofort auf einen Messwert korrigieren, der noch vom Umschalten
            # stammt - etwa beim Start, wenn das Geraet aus dem Auto-Modus kommt.
            self._mark_command_sent()

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
            # Deckel angehoben oder unveraendert: der naechste Regeltakt nutzt
            # den neuen Spielraum von selbst.
            return

        _LOGGER.info(
            "Deckel auf %s W gesenkt - Sollwert sofort von %s W auf "
            "\033[1m%s W\033[0m begrenzt",
            cap,
            int(current),
            cap,
        )
        ctrl["regulation_output"] = cap
        self._publish_state(GRP_ENERGY_CONTROL)
        if self._apply_mode(refresh=False):
            self._mark_command_sent()

    def _set_self_regulation(self, enabled: bool) -> None:
        ctrl = self.states[GRP_ENERGY_CONTROL]
        ctrl["self_regulation"] = enabled
        _LOGGER.info(
            "\033[1;36mSelbstregelung %s\033[0m",
            "aktiviert" if enabled else "deaktiviert",
        )
        if not enabled:
            ctrl["regulation_output"] = None
        self._mark_command_sent()
        self._publish_state(GRP_ENERGY_CONTROL)

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
        now = time.monotonic()
        self._last_regulation_input = now
        self._publish_state(GRP_ENERGY_CONTROL)

        # Messwerte sammeln; aelter als das doppelte Mittelungsfenster wird
        # nichts gebraucht.
        self._input_samples.append((now, value))
        grenze = now - 2 * max(1.0, self.s.self_regulation_average_window)
        while self._input_samples and self._input_samples[0][0] < grenze:
            self._input_samples.pop(0)

        if not self._regulation_active():
            self._log_input(
                "MQTT-Regelwert \033[1m%.1f W\033[0m - Selbstregelung ist aus", value
            )
            return
        if ctrl.get("applied_mode") != MODE_PASSIVE:
            self._log_input(
                "MQTT-Regelwert \033[1m%.1f W\033[0m - Passive-Modus ist nicht "
                "aktiv, kein Kommando",
                value,
            )
            return

        self._log_input(
            "MQTT-Regelwert \033[1m%.1f W\033[0m (Halteband %s-%s W) | Sollwert "
            "%s W | Deckel %s W",
            value,
            self.s.self_regulation_band_low,
            self.s.self_regulation_reserve,
            ctrl.get("regulation_output") or 0,
            max(0, int(ctrl.get("passive_power", 0))),
        )

    def _log_input(self, message: str, *args: Any) -> None:
        """Eingangswerte ausgeduennt protokollieren.

        Bei einem Messwert pro Sekunde waere sonst jede Sekunde eine Zeile
        faellig. Auf CALC erscheint der Rechenweg der Regeltakte ohnehin
        vollstaendig.
        """
        now = time.monotonic()
        if now - self._last_input_log < QUIET_LOG_INTERVAL:
            return
        self._last_input_log = now
        _LOGGER.info(message, *args)

    def _input_mean(self) -> float | None:
        """Mittel der Messwerte im Mittelungsfenster.

        Beruecksichtigt nur Werte, die *nach* dem letzten Kommando eingetroffen
        sind - waehrend das Geraet noch auf die alte Vorgabe hinlaeuft, ist ein
        Messwert nichts wert. Deckt das Fenster noch keine volle
        ``average_window`` ab, kommt ``None`` zurueck.
        """
        fenster = max(1.0, self.s.self_regulation_average_window)
        now = time.monotonic()
        frisch = [
            v
            for t, v in self._input_samples
            if t >= self._last_passive_push and t >= now - fenster
        ]
        if len(frisch) < 2:
            return None
        aeltester = min(
            t
            for t, _ in self._input_samples
            if t >= self._last_passive_push and t >= now - fenster
        )
        if now - aeltester < fenster * 0.8:
            return None
        return sum(frisch) / len(frisch)

    def _compute_regulation_output(
        self, value: float, gain: float, margin_percent: float = 0.0
    ) -> int:
        """Aus der Netzleistung den naechsten Sollwert berechnen.

        Zwischen ``band_low`` und ``reserve`` liegt ein Halteband, in dem gar
        nicht geregelt wird: ein Netzbezug unterhalb der Reserve ist besser als
        die Reserve selbst. Ausserhalb wird in beide Richtungen auf die Reserve
        zurueckgeregelt, um den Anteil ``gain`` der Abweichung.

        ``margin_percent`` zieht zusaetzlich einen Anteil des neuen Sollwerts
        ab - genutzt bei der Einspeise-Korrektur, damit das Ergebnis eher im
        Netzbezug landet als erneut im Negativen.
        """
        ctrl = self.states[GRP_ENERGY_CONTROL]
        base = int(ctrl.get("regulation_output") or 0)

        reserve = self.s.self_regulation_reserve
        low = self.s.self_regulation_band_low
        if value > reserve:
            error = value - reserve
            abstand = value - reserve
        elif value < low:
            # Korrigiert wird auf die Reserve, gemessen wird der Abstand zum
            # Band - sonst enthielte schon die kleinste Einspeisung die volle
            # Reserve und das Totband koennte nach unten nie greifen.
            error = value - reserve
            abstand = value - low
        else:
            error = 0.0
            abstand = 0.0
        self._last_in_band = error == 0.0

        step = error * gain
        # Der Aufschlag bezieht sich auf die Korrektur, nicht auf den Sollwert.
        # Sonst waere er bei hohem Sollwert und winziger Einspeisung riesig -
        # 5 % von 300 W sind 15 W, egal ob 0,5 W oder 200 W eingespeist wurden.
        if margin_percent > 0 and step < 0:
            step *= 1.0 + margin_percent / 100.0
        raw = base + step
        out = self._clamp_setpoint(raw, base)
        self._last_calc = {
            "value": value,
            "error": error,
            "distance": abstand,
            "step": step,
            "gain": gain,
            "base": base,
            "cap": self._current_cap(),
            "out": out,
        }
        return out

    def _current_cap(self) -> int:
        ctrl = self.states[GRP_ENERGY_CONTROL]
        return max(0, min(self.s.passive_power_max, int(ctrl.get("passive_power", 0))))

    def _clamp_setpoint(self, raw: float, base: int) -> int:
        """Auf Deckel, Null und Grundlast begrenzen."""
        cap = self._current_cap()
        out = int(max(0, min(cap, round(raw))))
        self._last_target_saturated = raw > cap or raw < 0

        # Untergrenze Grundlast: so viel wird auf der Phase ohnehin verbraucht.
        # Sie bremst nur den Schritt von oben - wird danach immer noch
        # Einspeisung gemessen, steht der Sollwert bereits auf der Grundlast und
        # der naechste Schritt darf darunter. Eine zu hoch eingestellte
        # Grundlast kann so keine dauerhafte Einspeisung erzwingen.
        floor = self.s.self_regulation_base_load
        self._last_floor_applied = False
        if 0 < floor < base and out < floor:
            out = int(min(cap, floor))
            self._last_floor_applied = True
        return out

    def _deadband_for(self, error: float) -> float:
        """Totband, abhaengig vom aktuellen Leistungsniveau.

        Bei hoher Leistung sind kleine Abweichungen relativ bedeutungslos, und
        jede Korrektur kostet ein Kommando. ``deadband_percent`` skaliert das
        Totband deshalb linear mit dem Sollwert, mit dem Grundwert als
        Untergrenze. Nach unten gilt immer der Grundwert - sonst wuerde bei
        hohem Sollwert eine kleine Einspeisung stillschweigend toleriert.
        """
        grund = float(self.s.self_regulation_deadband)
        anteil = self.s.self_regulation_deadband_percent
        if anteil <= 0 or error < 0:
            return grund
        ctrl = self.states[GRP_ENERGY_CONTROL]
        sollwert = abs(int(ctrl.get("regulation_output") or 0))
        return max(grund, sollwert * anteil / 100.0)

    def _log_calculation(self, grund: str) -> None:
        """Den Rechenweg eines Regeltakts nachvollziehbar machen."""
        c = self._last_calc
        if not c or not _LOGGER.isEnabledFor(CALC_LEVEL):
            return
        if self._last_in_band:
            lage = "im Halteband"
        elif self._last_floor_applied:
            lage = f"auf die Grundlast {self.s.self_regulation_base_load} W begrenzt"
        elif self._last_target_saturated:
            lage = "am Anschlag begrenzt"
        else:
            lage = f"{c['gain'] * 100:.0f}% der Abweichung"
        _LOGGER.log(
            CALC_LEVEL,
            "%s: Mittel %.1f W | Band %s-%s W | Abstand %+.1f W | "
            "Abweichung %+.1f W | Schritt %+.1f W (%s) | %s -> %s W | "
            "Deckel %s W",
            grund,
            c["value"],
            self.s.self_regulation_band_low,
            self.s.self_regulation_reserve,
            c.get("distance", 0.0),
            c["error"],
            c["step"],
            lage,
            c["base"],
            c["out"],
            c["cap"],
        )

    # -- Regeltakt -------------------------------------------------------
    def _keepalive_interval(self) -> float:
        """Laenge eines Regeltakts.

        Der Passive-Modus laeuft nach ``cd_time`` aus, es muss also ohnehin
        regelmaessig ein Kommando raus. Genau dieser Takt ist der Regeltakt -
        ein eigener Zeitplan waere nur eine zweite Uhr fuer dieselbe Sache.
        """
        ctrl = self.states[GRP_ENERGY_CONTROL]
        cd = int(ctrl.get("passive_cd_time", self.s.passive_cd_time_default) or 0)
        if cd <= 0:
            return 0.0
        interval = self.s.passive_keepalive_interval
        if interval <= 0:
            interval = cd / 2.0
        return max(1.0, interval)

    def _check_cycle_timing(self, grund: str = "") -> None:
        """Pruefen, ob zwischen Regeltakt und cd_time genug Reserve liegt.

        Das Geraet faellt aus dem Passive-Modus, wenn laenger als ``cd_time``
        kein Kommando kommt. Liegt der Takt dicht darunter, reicht ein
        einzelner verlorener UDP-Frame: Der naechste Versuch braucht ein paar
        Sekunden, und die Frist ist abgelaufen.

        Geprueft wird gegen die **tatsaechlich eingestellte** cd_time aus der
        Number-Entity, nicht gegen den Konfigurationswert - der kann durch
        ``restore_state`` oder eine Aenderung zur Laufzeit davon abweichen.
        Deshalb laeuft die Pruefung auch nicht nur beim Start.
        """
        ctrl = self.states[GRP_ENERGY_CONTROL]
        cd = int(ctrl.get("passive_cd_time", self.s.passive_cd_time_default) or 0)
        takt = self._keepalive_interval()
        if cd <= 0 or takt <= 0:
            return
        if cd >= 2 * takt:
            return
        jetzt = time.monotonic()
        if not grund and jetzt - self._timing_warned < 600:
            return
        self._timing_warned = jetzt
        _LOGGER.warning(
            "Knappes Timing%s: Regeltakt %.0fs bei cd_time %ss - nur %.0fs "
            "Reserve. Ein einzelnes verlorenes Kommando wirft das Geraet aus "
            "dem Passive-Modus. Empfehlung: cd_time auf mindestens %.0fs, "
            "oder request_retries auf 1",
            f" ({grund})" if grund else "",
            takt,
            cd,
            cd - takt,
            2 * takt,
        )

    def _cycle_reserve(self) -> float:
        """Zeit, die die Abfrage vor dem Kommando braucht.

        Mindestpause zwischen zwei Anfragen plus Antwortzeit. Um genau diese
        Spanne startet der Takt frueher, damit das Kommando puenktlich zum
        Intervall rausgeht - sonst schoebe sich jeder Takt um die Dauer der
        Abfrage nach hinten und die Marge zur cd_time schrumpft.
        """
        return self.s.request_delay + self.s.request_timeout

    def _passive_cycle(self) -> None:
        """Einmal je Takt: regeln und senden, oder nur nachsenden."""
        if not self._initialized:
            return
        ctrl = self.states[GRP_ENERGY_CONTROL]
        if ctrl.get("applied_mode") != MODE_PASSIVE:
            return
        # Bei aktiver Selbstregelung ist das Nachsenden zwingend, sonst laeuft
        # der Countdown des Geraets ab, sobald keine neuen Werte kommen.
        if not (self.s.passive_keepalive or self._regulation_active()):
            return
        interval = self._keepalive_interval()
        if interval <= 0:
            return
        reserve = 0.0
        if self._regulation_active():
            reserve = min(self._cycle_reserve(), max(0.0, interval - 1.0))
        if time.monotonic() - self._last_passive_push < interval - reserve:
            return

        if not self._regulation_active():
            _LOGGER.log(
                CALC_LEVEL,
                "Passive-Keepalive: %s W erneut gesendet (alle %.0fs)",
                self._effective_passive_power(),
                interval,
            )
            self._apply_mode(refresh=False)
            return

        # Nach einem Fehlschlag einen Takt lang nur senden. Die Abfrage wuerde
        # das Kommando um ihre Antwortzeit verzoegern - und genau die fehlt,
        # wenn das Geraet ohnehin schon nicht antwortet.
        if self._skip_query_once:
            self._skip_query_once = False
            _LOGGER.log(
                CALC_LEVEL,
                "Letzter Request fehlgeschlagen - Abfrage uebersprungen, "
                "Sollwert %s W wird direkt gesendet",
                self._effective_passive_power(),
            )
            self._apply_mode(refresh=False)
            return

        # Unmittelbar vor dem Kommando den Zustand des Geraets lesen. Zu diesem
        # Zeitpunkt ist es auf die aktuelle Vorgabe eingeschwungen, die Meldung
        # gehoert also zur richtigen Vorgabe - anders als eine Abfrage kurz
        # nach dem Kommando, die noch den alten Zustand zeigt.
        if not self._step_es_status():
            _LOGGER.warning(
                "ES.GetStatus vor dem Regeltakt fehlgeschlagen - keine "
                "Korrektur, Sollwert %s W wird erneut gesendet",
                self._effective_passive_power(),
            )
            self._apply_mode(refresh=False)
            return

        # Erst den Verdacht des letzten Takts entscheiden, dann neu pruefen.
        self._resolve_output_suspect()
        fehlend = self._check_device_output()
        if fehlend > 0:
            self._note_output_suspect(fehlend)
            self._input_samples.clear()
            self._cycle_mean = None
            self._cycle_delta = 0
            self._apply_mode(refresh=False)
            return

        self._regulate()

    def _check_device_output(self) -> float:
        """Vergleicht die gemeldete Ausgangsleistung mit der Erwartung.

        Das Geraet stellt nicht exakt den vorgegebenen Wert ein - zwischen
        Vorgabe und ``ongrid_power`` liegt ein weitgehend konstanter Verlust
        (gemessen rund 15 W bei 130 W wie bei 300 W Vorgabe, also absolut und
        nicht proportional). Dieser Offset wird als gleitender Mittelwert
        gelernt, beginnend beim ersten Messwert.

        Liegt die Meldung deutlich unter ``Vorgabe - Offset``, hat das Geraet
        seinen Ausgang eigenmaechtig reduziert. Der Anstieg an der
        Leistungsklemme ist dann dem Speicher zuzuschreiben und nicht einem
        Verbraucher - die Messwerte des Mittelungsfensters sind unbrauchbar.

        Rueckgabe: fehlende Leistung in Watt, 0 wenn alles in Ordnung ist.
        """
        schwelle = self.s.self_regulation_underdelivery
        if schwelle <= 0 or self._last_ongrid is None:
            return 0.0
        gemeldet = self._last_ongrid[0]
        soll = int(self.states[GRP_ENERGY_CONTROL].get("regulation_output") or 0)
        if soll <= 0:
            return 0.0

        if self._loss_offset is None:
            self._loss_offset = max(0.0, soll - gemeldet)
            _LOGGER.log(
                CALC_LEVEL,
                "Verlust gelernt: Vorgabe %s W, gemeldet %.0f W -> Offset %.1f W",
                soll,
                gemeldet,
                self._loss_offset,
            )
            return 0.0

        erwartet = soll - self._loss_offset
        fehlend = erwartet - gemeldet
        if fehlend >= schwelle:
            return fehlend

        # Plausibel: Offset nachfuehren (gleitender Mittelwert).
        self._loss_offset = 0.8 * self._loss_offset + 0.2 * max(0.0, soll - gemeldet)
        _LOGGER.log(
            CALC_LEVEL,
            "Geraet liefert %.0f W bei Vorgabe %s W (erwartet %.0f W, "
            "Offset %.1f W)",
            gemeldet,
            soll,
            erwartet,
            self._loss_offset,
        )
        return 0.0

    def _regulate(self) -> None:
        """Einen Regelschritt ausfuehren und das Kommando senden.

        Liegt der Mittelwert unter ``band_low``, wird mit voller Verstaerkung
        und zusaetzlichem Aufschlag korrigiert - Einspeisung soll in einem
        Schritt beendet sein und das Ergebnis eher im Netzbezug landen.
        Ansonsten gilt die gedaempfte Verstaerkung.
        """
        ctrl = self.states[GRP_ENERGY_CONTROL]

        # Stillgelegt: nur den Passive-Modus halten, nicht regeln.
        if self._stuck_value is not None:
            self._log_quiet(
                "Regelsignal ruht - Sollwert %s W wird nur nachgesendet",
                self._effective_passive_power(),
            )
            self._apply_mode(refresh=False)
            return

        mittel = self._input_mean()
        if mittel is None:
            _LOGGER.log(
                CALC_LEVEL,
                "Kein vollstaendiges Mittelungsfenster - Sollwert %s W wird nur "
                "nachgesendet",
                self._effective_passive_power(),
            )
            self._apply_mode(refresh=False)
            return

        self._check_input_stuck(mittel)
        if self._stuck_value is not None:
            return

        vorher = int(ctrl.get("regulation_output") or 0)
        export = mittel < self.s.self_regulation_band_low

        if export:
            out = self._compute_regulation_output(
                mittel, gain=1.0, margin_percent=self.s.self_regulation_export_margin
            )
            grund = (
                f"Einspeisung {mittel:.1f} W, Reserve "
                f"{self.s.self_regulation_export_margin:.0f}%"
            )
        else:
            out = self._compute_regulation_output(
                mittel, gain=self.s.self_regulation_gain
            )
            grund = "Regeltakt"

        error = float(self._last_calc.get("error", 0.0))
        abstand = float(self._last_calc.get("distance", 0.0))
        totband = self._deadband_for(error)
        if abs(abstand) < totband:
            out = vorher
            self._last_calc["out"] = out
            grund = (
                f"{'Einspeisung' if export else 'Regeltakt'}, Abstand zum Band "
                f"{abstand:+.1f} W im Totband {totband:.0f} W"
            )

        self._log_calculation(grund)
        ctrl["regulation_output"] = out
        if out != vorher:
            _LOGGER.log(
                CALC_LEVEL, "Korrektur (%s): %s W -> %s W", grund, vorher, out
            )
        self._publish_state(GRP_ENERGY_CONTROL)

        if self._apply_mode(refresh=False):
            self._cycle_mean = mittel
            self._cycle_delta = out - vorher
        else:
            _LOGGER.warning(
                "Sollwert %s W konnte nicht gesendet werden - zurueck auf %s W",
                out,
                vorher,
            )
            ctrl["regulation_output"] = vorher
            self._publish_state(GRP_ENERGY_CONTROL)

    # -- Ueberwachung des Regelsignals -----------------------------------
    def _check_input_stuck(self, mittel: float) -> None:
        """Erkennen, wenn der Messwert auf Kommandos nicht reagiert.

        Publiziert ein Sensor weiter, liefert aber immer denselben Wert, greift
        ``input_timeout`` nicht und die Regelung wuerde den Sollwert Takt fuer
        Takt bis zum Deckel hochtreiben - und dabei unbemerkt einspeisen.
        Gezaehlt wird nur, wenn der vorige Takt eine deutliche Aenderung
        befohlen hat.
        """
        grenze = self.s.self_regulation_stuck_limit
        if grenze <= 0 or self._cycle_mean is None:
            return
        deutlich = abs(self._cycle_delta) >= 3 * max(
            1.0, float(self.s.self_regulation_deadband)
        )
        if not deutlich:
            return
        if abs(mittel - self._cycle_mean) >= 1.0:
            self._reaction_failures = 0
            return

        self._reaction_failures += 1
        _LOGGER.warning(
            "Messwert unveraendert bei %.1f W, obwohl %+.0f W befohlen wurden "
            "- Ausfall %s/%s",
            mittel,
            self._cycle_delta,
            self._reaction_failures,
            grenze,
        )
        if self._reaction_failures >= grenze:
            self._declare_stuck(mittel)

    def _declare_stuck(self, value: float) -> None:
        """Regelsignal als unbrauchbar einstufen und stillegen."""
        ctrl = self.states[GRP_ENERGY_CONTROL]
        self._stuck_value = value
        self._reaction_failures = 0
        grund = (
            f"Regelsignal reagiert nicht - {self.s.self_regulation_stuck_limit} "
            f"Takte ohne Bewegung, Messwert steht bei {value:.1f} W"
        )
        _LOGGER.error(
            "\033[1;31m%s\033[0m. Sollwert wird auf 0 W gesetzt, die Regelung "
            "ruht bis sich der Messwert wieder bewegt.",
            grund,
        )
        self._regulation_fault = grund
        ctrl["regulation_signal"] = SIGNAL_STUCK
        ctrl["regulation_output"] = 0
        self._publish_state(GRP_ENERGY_CONTROL)
        self._apply_mode(refresh=False)

    def _check_stuck_recovery(self) -> None:
        """Wieder anlaufen, sobald sich der Messwert bewegt."""
        if self._stuck_value is None:
            return
        letzter = self.states[GRP_ENERGY_CONTROL].get("regulation_input")
        if letzter is None:
            return
        if abs(float(letzter) - self._stuck_value) <= max(
            2.0, float(self.s.self_regulation_deadband)
        ):
            self._log_quiet(
                "Regelsignal steht weiterhin bei %.1f W - Regelung ruht",
                float(letzter),
            )
            return
        _LOGGER.info(
            "\033[1;32mRegelsignal bewegt sich wieder\033[0m (%.1f W statt "
            "%.1f W) - Regelung nimmt den Betrieb auf",
            float(letzter),
            self._stuck_value,
        )
        self._stuck_value = None
        self._regulation_fault = None
        self._cycle_mean = None
        self.states[GRP_ENERGY_CONTROL]["regulation_signal"] = SIGNAL_OK
        self._publish_state(GRP_ENERGY_CONTROL)

    def _log_quiet(self, message: str, *args: Any) -> None:
        """Wiederkehrende "nichts passiert"-Meldungen ausduennen."""
        now = time.monotonic()
        if now - self._last_quiet_log < QUIET_LOG_INTERVAL:
            return
        self._last_quiet_log = now
        _LOGGER.log(CALC_LEVEL, message, *args)

    def _mark_command_sent(self) -> None:
        """Nach einem Sollwert von aussen (Deckel, Timeout) den Takt neu starten."""
        self._input_samples.clear()
        self._cycle_mean = None
        self._cycle_delta = 0

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
        self._publish_state(GRP_ENERGY_CONTROL)
        if self._apply_mode(refresh=False):
            self._mark_command_sent()

    # =================================================================
    # Lade- und Entladeplanung (rechnet und meldet, greift nicht ein)
    # =================================================================
    @property
    def forecast_topic(self) -> str:
        """Topic der PV-Prognose fuer morgen."""
        custom = (self.s.plan_forecast_topic or "").strip()
        return custom or f"{self.s.base_topic}/{GRP_ENERGY_PLAN}/forecast"

    def _on_forecast_value(self, payload: str) -> None:
        wert = self._parse_number(payload)
        if wert is None:
            _LOGGER.warning("PV-Prognose nicht lesbar: %r", payload[:80])
            return
        self.states[GRP_ENERGY_PLAN]["forecast_tomorrow"] = round(wert, 1)
        _LOGGER.log(PLAN_LEVEL, "PV-Prognose fuer morgen: %.0f Wh", wert)
        self._update_plan()

    def _pv_start_in(self) -> float | None:
        """Stunden bis zum naechsten PV-Beginn."""
        uhrzeit = _parse_clock(self.s.plan_pv_start)
        if uhrzeit is None:
            return None
        jetzt = datetime.now()
        ziel = jetzt.replace(
            hour=uhrzeit.hour, minute=uhrzeit.minute, second=0, microsecond=0
        )
        if ziel <= jetzt:
            ziel += timedelta(days=1)
        return (ziel - jetzt).total_seconds() / 3600.0

    def _in_pv_window(self) -> bool:
        """True zwischen ``plan_pv_start`` und ``plan_pv_end``.

        In dieser Zeit ist die Flugbahn ohne Aussage: Sie schreibt den
        Verbrauch bis zum naechsten PV-Beginn fort und kennt die PV nicht, die
        gerade laedt. Der Planer meldet deshalb ``pv`` und laesst die
        Fortschreibung aus.
        """
        start = _parse_clock(self.s.plan_pv_start)
        ende = _parse_clock(self.s.plan_pv_end)
        if start is None or ende is None:
            return False
        jetzt = datetime.now().time()
        if start <= ende:
            im_fenster = start <= jetzt < ende
        else:  # Fenster ueber Mitternacht
            im_fenster = jetzt >= start or jetzt < ende
        if not im_fenster:
            return False

        # Zusaetzlich muss tatsaechlich etwas ankommen. An einem trueben Tag
        # liegt das Fenster zwar offen, die Flugbahn waere aber durchaus
        # aussagekraeftig. Nachgelaufen wird mit zehn Minuten Haltezeit, damit
        # eine vorbeiziehende Wolke den Zustand nicht hin und her kippt.
        if self._pv_last_seen is None:
            return False
        return time.monotonic() - self._pv_last_seen <= PV_HOLD_SECONDS

    def _house_load(self) -> float | None:
        """Last, die der Speicher deckt: Netzwert plus seine Ausgangsleistung.

        Der Netzwert kommt von der Messklemme, die Ausgangsleistung aus
        ``ES.GetStatus``. Die Summe ist der Verbrauch auf der Phase, an der der
        Speicher haengt - und damit die Groesse, die ueber die Entladedauer
        entscheidet.
        """
        netz = self.states[GRP_ENERGY_CONTROL].get("regulation_input")
        if netz is None or self._last_ongrid is None:
            return None
        return max(0.0, float(netz) + max(0.0, self._last_ongrid[0]))

    def _load_average(self) -> float | None:
        """Mittlere Last ueber ``plan_load_window``.

        Die Flugbahn wird ueber viele Stunden fortgeschrieben - dafuer ist der
        Momentanwert unbrauchbar. Ein Kuehlschrank, der gerade anlaeuft, wuerde
        sonst die halbe Nacht hochgerechnet.
        """
        fenster = max(60, self.s.plan_load_window)
        jetzt = time.monotonic()
        werte = [w for t, w in self._load_samples if t >= jetzt - fenster]
        if not werte:
            return None
        return sum(werte) / len(werte)

    def _learn_base_load(self, last: float) -> None:
        """Grundlast aus den ruhigen Nachtstunden mitteln.

        Zwischen 1 und 5 Uhr laeuft erfahrungsgemaess nur die Grundlast. Der
        Wert wird ueber mehrere Naechte geglaettet, damit ein einzelner
        Verbraucher ihn nicht verzerrt.
        """
        if not 1 <= datetime.now().hour < 5:
            return
        plan = self.states[GRP_ENERGY_PLAN]
        bisher = plan.get("base_load")
        neu = last if bisher is None else 0.95 * float(bisher) + 0.05 * last
        plan["base_load"] = round(neu, 1)

    def _check_grid_charging(self) -> None:
        """Erkennen, ob der Speicher gerade aus dem Netz laedt.

        Unterschieden wird zwischen gewollt - wir haben eine negative Leistung
        befohlen - und eigenmaechtig. Letzteres ist der Fall, den dieser Test
        beobachten soll: Das Geraet laedt sich nach, obwohl es entladen
        sollte. Der SOC dieses Moments bleibt stehen, damit er spaeter
        ablesbar ist.
        """
        if self._last_ongrid is None:
            return
        plan = self.states[GRP_ENERGY_PLAN]
        leistung = self._last_ongrid[0]
        schwelle = self.s.plan_charge_threshold
        laedt = leistung <= -schwelle

        if not laedt:
            if plan.get("charging"):
                _LOGGER.log(PLAN_LEVEL, "Ladung aus dem Netz beendet")
            plan["charging"] = False
            plan["charging_type"] = CHARGE_OFF
            return

        befohlen = self._effective_passive_power()
        art = CHARGE_INTENDED if befohlen < 0 else CHARGE_UNEXPECTED
        vorher = plan.get("charging_type")
        plan["charging"] = True
        plan["charging_type"] = art

        if art == vorher:
            return
        if art == CHARGE_INTENDED:
            _LOGGER.log(
                PLAN_LEVEL,
                "Gewollte Ladung aus dem Netz: %.0f W (befohlen %s W)",
                -leistung,
                befohlen,
            )
            return

        soc = self.states[GRP_ENERGY_STATUS].get("bat_soc")
        plan["charge_soc"] = soc
        plan["charge_power"] = round(-leistung)
        plan["charge_since"] = _utcnow()
        _LOGGER.warning(
            "\033[1;33mSelbstnachladung erkannt\033[0m bei SOC %s %% - Geraet "
            "laedt mit %.0f W, befohlen waren %s W",
            soc,
            -leistung,
            befohlen,
        )

    def _check_day_rollover(self) -> None:
        """Tagesabschluss: Prognose mit der tatsaechlichen Produktion vergleichen.

        Die Prognose gilt fuer den naechsten Tag. Beim Datumswechsel wird sie
        zur Prognose des laufenden Tages und der Stand des PV-Zaehlers
        festgehalten. Am naechsten Wechsel steht fest, was wirklich produziert
        wurde - daraus lernt die Bridge einen Faktor.

        Der Faktor fasst zwei Dinge zusammen, die sich ohnehin nicht trennen
        lassen: wie gut die Prognose trifft und wieviel davon ueberhaupt am
        Speicher ankommt. Genau das braucht man fuer die Platzrechnung.
        """
        heute = datetime.now().date().isoformat()
        if self._plan_day == heute:
            return

        plan = self.states[GRP_ENERGY_PLAN]
        if self._plan_day is not None and self._pv_day_start is not None:
            produziert = max(0.0, self._pv_energy_wh - self._pv_day_start)
            plan["pv_today"] = round(produziert)
            prognose = self._forecast_today
            if prognose and prognose > 100 and produziert > 100:
                faktor = produziert / prognose * 100.0
                bisher = plan.get("forecast_factor")
                neu = faktor if bisher is None else 0.7 * float(bisher) + 0.3 * faktor
                plan["forecast_factor"] = round(neu, 1)
                _LOGGER.log(
                    PLAN_LEVEL,
                    "Tagesabschluss %s: Prognose %.0f Wh, produziert %.0f Wh "
                    "-> Faktor %.0f %% (geglaettet %.0f %%)",
                    self._plan_day,
                    prognose,
                    produziert,
                    faktor,
                    neu,
                )
            else:
                _LOGGER.log(
                    PLAN_LEVEL,
                    "Tagesabschluss %s: produziert %.0f Wh - zu wenig Daten "
                    "fuer einen Faktor",
                    self._plan_day,
                    produziert,
                )

        self._plan_day = heute
        self._pv_day_start = self._pv_energy_wh
        self._forecast_today = plan.get("forecast_tomorrow")
        plan["pv_today"] = 0
        self._save_plan_state(sofort=True)

    def _note_output_suspect(self, fehlend: float) -> None:
        """Einen Einbruch von ``ongrid_power`` vormerken, noch nicht bewerten.

        Eine einzelne Null in der Geraeteantwort kann ein Messfehler sein - das
        Geraet liefert gelegentlich einen unbrauchbaren Wert und meldet einen
        Takt spaeter wieder normal. Entschieden wird deshalb erst im naechsten
        Takt anhand der Messklemme: Hat der Speicher wirklich aufgehoert zu
        liefern, muss der Netzbezug um die fehlende Leistung steigen.
        """
        klemme = self.states[GRP_ENERGY_CONTROL].get("regulation_input")
        self._output_suspect = {
            "fehlend": fehlend,
            "gemeldet": self._last_ongrid[0] if self._last_ongrid else 0.0,
            "klemme": float(klemme) if klemme is not None else 0.0,
        }
        _LOGGER.log(
            CALC_LEVEL,
            "Verdacht: Geraet meldet %.0f W statt erwarteter %.0f W. Korrektur "
            "ausgesetzt, Bewertung im naechsten Takt (Klemme steht bei %.0f W)",
            self._output_suspect["gemeldet"],
            self._output_suspect["gemeldet"] + fehlend,
            self._output_suspect["klemme"],
        )

    def _resolve_output_suspect(self) -> None:
        """Den Verdacht des letzten Takts anhand der Messklemme entscheiden."""
        verdacht = self._output_suspect
        if verdacht is None:
            return
        self._output_suspect = None

        plan = self.states[GRP_ENERGY_PLAN]
        klemme = self.states[GRP_ENERGY_CONTROL].get("regulation_input")
        jetzt = float(klemme) if klemme is not None else 0.0
        anstieg = jetzt - verdacht["klemme"]
        # Die Haelfte der fehlenden Leistung reicht als Nachweis - die Klemme
        # mittelt und der Speicher laeuft nach dem naechsten Kommando wieder an.
        noetig = verdacht["fehlend"] * 0.5

        if anstieg >= noetig:
            plan["output_dropouts"] = int(plan.get("output_dropouts") or 0) + 1
            plan["last_dropout"] = _utcnow()
            _LOGGER.warning(
                "\033[1;33mAusfall bestaetigt\033[0m: Geraet hatte %.0f W zu "
                "wenig geliefert, der Netzbezug stieg um %.0f W (noetig waren "
                "%.0f W). Gesamt bisher: %s",
                verdacht["fehlend"],
                anstieg,
                noetig,
                plan["output_dropouts"],
            )
        else:
            plan["output_glitches"] = int(plan.get("output_glitches") or 0) + 1
            _LOGGER.log(
                CALC_LEVEL,
                "Messfehler: Geraet meldete %.0f W, der Netzbezug stieg aber "
                "nur um %.0f W (noetig waren %.0f W) - der Speicher hat "
                "durchgehend geliefert. Gesamt bisher: %s",
                verdacht["gemeldet"],
                anstieg,
                noetig,
                plan["output_glitches"],
            )
        self._save_plan_state(sofort=True)

    def _update_plan(self) -> None:
        """Flugbahn des Speichers bis zum PV-Beginn fortschreiben."""
        if not self.s.plan_enabled:
            return
        self._check_day_rollover()
        plan = self.states[GRP_ENERGY_PLAN]
        status = self.states[GRP_ENERGY_STATUS]
        soc = status.get("bat_soc")
        kapazitaet = status.get("bat_cap")
        stunden = self._pv_start_in()

        plan["target_soc"] = self.s.plan_target_soc
        plan["hours_until_pv"] = None if stunden is None else round(stunden, 2)

        last = self._house_load()
        if last is not None:
            jetzt = time.monotonic()
            self._load_samples.append((jetzt, last))
            grenze = jetzt - max(60, self.s.plan_load_window)
            while self._load_samples and self._load_samples[0][0] < grenze:
                self._load_samples.pop(0)
            plan["current_load"] = round(last, 1)
            plan["load_average"] = round(self._load_average() or last, 1)
            self._learn_base_load(last)
        plan["loss_offset"] = (
            None if self._loss_offset is None else round(self._loss_offset, 1)
        )

        if soc is None or kapazitaet is None or stunden is None or not kapazitaet:
            plan["plan_status"] = PLAN_NO_DATA
            self._publish_group(GRP_ENERGY_PLAN, PLAN_ENTITIES)
            return

        pro_prozent = float(kapazitaet) / 100.0
        nutzbar = max(0.0, (float(soc) - self.s.plan_target_soc) * pro_prozent)
        plan["usable_energy"] = round(nutzbar)
        plan["required_cap"] = round(nutzbar / stunden) if stunden > 0 else 0

        # Waehrend der PV-Produktion ist die Fortschreibung ohne Aussage: Sie
        # kennt nur den Verbrauch, nicht die Energie, die gerade einlaedt.
        if self._in_pv_window():
            plan["hours_until_pv"] = 0.0
            plan["projected_soc"] = None
            plan["limit_reached_at"] = None
            plan["plan_status"] = PLAN_PV
            self._update_room(plan, pro_prozent, float(soc))
            self._save_plan_state()
            self._publish_group(GRP_ENERGY_PLAN, PLAN_ENTITIES)
            self._log_plan()
            return

        # Fortschreibung mit der geglaetteten Last; fehlt sie, mit der
        # gelernten Grundlast.
        rechenlast = plan.get("load_average") or plan.get("base_load")
        if rechenlast:
            verbraucht = float(rechenlast) * stunden
            projiziert = float(soc) - verbraucht / pro_prozent
            plan["projected_soc"] = round(projiziert, 1)
            if projiziert < self.s.plan_target_soc and float(rechenlast) > 0:
                reicht = nutzbar / float(rechenlast)
                plan["limit_reached_at"] = (
                    datetime.now(UTC) + timedelta(hours=reicht)
                ).isoformat(timespec="seconds")
                plan["plan_status"] = PLAN_LIMIT
            else:
                plan["limit_reached_at"] = None
                plan["plan_status"] = PLAN_OK
        else:
            plan["projected_soc"] = None
            plan["limit_reached_at"] = None
            plan["plan_status"] = PLAN_NO_DATA

        self._update_room(plan, pro_prozent, plan.get("projected_soc"))

        self._save_plan_state()
        self._publish_group(GRP_ENERGY_PLAN, PLAN_ENTITIES)
        self._log_plan()

    def _update_room(
        self, plan: dict[str, Any], pro_prozent: float, soc: float | None
    ) -> None:
        """Platz fuer die erwartete PV-Energie rechnen.

        Vor dem PV-Beginn wird gegen den projizierten SOC gerechnet und gegen
        die ganze Prognose. Waehrend der Produktion gegen den tatsaechlichen
        SOC und gegen das, was von der Prognose noch aussteht - dann steht dort
        eine Live-Antwort auf die Frage, ob heute noch etwas verschenkt wird.

        Gerechnet wird mit der korrigierten Prognose, sofern ein Faktor gelernt
        wurde; die Rohprognose bleibt daneben sichtbar.
        """
        if self._pv_day_start is not None:
            plan["pv_today"] = round(max(0.0, self._pv_energy_wh - self._pv_day_start))

        prognose = plan.get("forecast_tomorrow")
        if prognose is None:
            return
        faktor = plan.get("forecast_factor")
        korrigiert = float(prognose) * (float(faktor) / 100.0 if faktor else 1.0)
        plan["forecast_corrected"] = round(korrigiert)

        if soc is None:
            return
        erwartet = korrigiert
        if self._in_pv_window():
            erwartet = max(0.0, korrigiert - float(plan.get("pv_today") or 0))
        platz = max(0.0, (100.0 - float(soc)) * pro_prozent)
        fehlt = max(0.0, erwartet - platz)
        plan["missing_room"] = round(fehlt)
        plan["expected_spill"] = round(fehlt)

    def _log_plan(self) -> None:
        if not _LOGGER.isEnabledFor(PLAN_LEVEL):
            return
        plan = self.states[GRP_ENERGY_PLAN]
        if plan.get("plan_status") == PLAN_NO_DATA:
            self._log_quiet("Planung: noch keine ausreichenden Daten")
            return
        _LOGGER.log(
            PLAN_LEVEL,
            "SOC %s %% | Grenze %s %% | nutzbar %s Wh | Last %s W "
            "(Grundlast %s W) | bis PV %s h",
            self.states[GRP_ENERGY_STATUS].get("bat_soc"),
            plan.get("target_soc"),
            plan.get("usable_energy"),
            plan.get("current_load"),
            plan.get("base_load"),
            plan.get("hours_until_pv"),
        )
        if plan.get("plan_status") == PLAN_PV:
            _LOGGER.log(
                PLAN_LEVEL,
                "PV laeuft (Fenster %s bis %s, aktuell %s W) - keine "
                "Flugbahn. Heute bisher %s Wh erzeugt, erwartet %s Wh",
                self.s.plan_pv_start,
                self.s.plan_pv_end,
                self.states[GRP_ENERGY_STATUS].get("pv_power"),
                plan.get("pv_today"),
                plan.get("forecast_corrected"),
            )
        elif plan.get("plan_status") == PLAN_LIMIT:
            _LOGGER.log(
                PLAN_LEVEL,
                "Flugbahn fuehrt unter die Grenze: projiziert %s %%, erreicht "
                "um %s | noetiger Deckel %s W, eingestellt %s W",
                plan.get("projected_soc"),
                plan.get("limit_reached_at"),
                plan.get("required_cap"),
                max(0, int(self.states[GRP_ENERGY_CONTROL].get("passive_power", 0))),
            )
        else:
            _LOGGER.log(
                PLAN_LEVEL,
                "Flugbahn in Ordnung: projiziert %s %% bei PV-Beginn | "
                "noetiger Deckel %s W",
                plan.get("projected_soc"),
                plan.get("required_cap"),
            )
        if plan.get("forecast_tomorrow") is not None:
            _LOGGER.log(
                PLAN_LEVEL,
                "Prognose morgen %s Wh (korrigiert %s Wh, Faktor %s %%) | "
                "fehlender Platz %s Wh | voraussichtlich verschenkt %s Wh",
                plan.get("forecast_tomorrow"),
                plan.get("forecast_corrected"),
                plan.get("forecast_factor"),
                plan.get("missing_room"),
                plan.get("expected_spill"),
            )

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
        if topic == self.forecast_topic:
            self._on_forecast_value(payload)
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
            self._check_cycle_timing("cd_time geaendert")
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

        self._check_stuck_recovery()
        self._check_cycle_timing()
        self._passive_cycle()
        self._check_regulation_timeout()
        self._sleep(0.2)

    def _regulation_busy(self) -> bool:
        """True, wenn eine Statusabfrage gerade stoeren wuerde.

        Frei ist das Fenster zwischen dem Kommando und dem Beginn des
        Mittelungsfensters. Danach sammelt die Bridge die Messwerte fuer den
        naechsten Takt und fragt kurz davor selbst den Geraetestatus ab - dort
        hat nichts anderes Platz.
        """
        if not self._regulation_active():
            return False
        ctrl = self.states[GRP_ENERGY_CONTROL]
        if ctrl.get("applied_mode") != MODE_PASSIVE:
            return False
        interval = self._keepalive_interval()
        if interval <= 0:
            return False
        frei_bis = (
            interval - self.s.self_regulation_average_window - self._cycle_reserve()
        )
        return time.monotonic() - self._last_passive_push >= frei_bis

    def _poll_jobs(self) -> list[tuple[str, int, Callable[[], bool]]]:
        """Die einzeln taktbaren Abfragen samt ihrem Intervall.

        Jede Abfrage hat ihr eigenes Intervall in Sekunden, ``0`` schaltet sie
        ab. Das ist noetig, weil die Abfragen sehr unterschiedlich interessant
        sind: ES.GetStatus liefert die laufenden Leistungswerte, Bat.GetStatus
        vor allem die Temperatur, ES.GetMode ist nach dem Start meist statisch
        und PV.GetStatus steckt in Teilen schon in ES.GetStatus.
        """
        es_status = self.s.poll_interval_es_status
        if self._regulation_active() and (
            self.states[GRP_ENERGY_CONTROL].get("applied_mode") == MODE_PASSIVE
        ):
            # Wird vor jedem Regeltakt ohnehin abgefragt.
            es_status = 0
        return [
            ("es_status", es_status, self._step_es_status),
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
            # Abfragen laufen im freien Fenster zwischen Kommando und
            # Mittelungsfenster. Verschoben wird aber nur so lange, bis die
            # Abfrage das Doppelte ihres Intervalls ueberfaellig ist - sonst
            # wuerde sie bei kurzem Regeltakt dauerhaft verhungern.
            if self._regulation_busy() and now - last < interval * 2:
                self._log_quiet(
                    "Abfrage %s verschoben - die Regelung arbeitet gerade",
                    name,
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
            self._note_request_failure()
            return
        self._watchdog_failures += 1
        self._note_request_failure()
        # Ein beschaeftigtes Geraet ist kein Kommunikationsausfall. Einzelne
        # Fehlschlaege werden deshalb nur gezaehlt; "Communication established"
        # wechselt erst, wenn die Schwelle erreicht ist.
        _LOGGER.warning(
            "%s fehlgeschlagen (%s) - Fehler %s/%s",
            method,
            err,
            self._watchdog_failures,
            self.s.watchdog_failure_threshold,
        )
        self.health.update(watchdog_failures=self._watchdog_failures)
        if self._watchdog_failures >= self.s.watchdog_failure_threshold:
            _LOGGER.error(
                "\033[1;31mWatchdog ausgeloest\033[0m: %s Fehler in Folge, "
                "das Geraet gilt als nicht erreichbar",
                self._watchdog_failures,
            )
            self._set_communication(False, str(err))
            first = self.health.snapshot().get("device_ok") is not False
            self.health.update(device_ok=False)
            self._initialized = False
            if first:
                _LOGGER.error(
                    "Health-Endpoint meldet unhealthy - Supervisor-Watchdog "
                    "startet das Add-on neu, sofern aktiviert"
                )

    def _note_request_failure(self) -> None:
        """Einen fehlgeschlagenen Request zaehlen und sichtbar machen."""
        sys_state = self.states[GRP_SYSTEM]
        sys_state["request_failures"] = int(sys_state.get("request_failures") or 0) + 1
        sys_state["last_failure"] = _utcnow()
        # Das Geraet ist gerade beschaeftigt. Im naechsten Takt hat das
        # Kommando Vorrang: Es haelt den Passive-Modus am Leben, waehrend die
        # Statusabfrage es nur um ihre Antwortzeit verzoegern und das Geraet
        # zusaetzlich belasten wuerde.
        self._skip_query_once = True
        self._publish_state(GRP_SYSTEM)

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
