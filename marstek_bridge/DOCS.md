# Marstek Self-consumption Bridge - Konfiguration

Die Optionen sind nach Themen gruppiert:

| Gruppe | Inhalt |
|---|---|
| `marstek_network_settings` | Erreichbarkeit des Speichers im LAN |
| `mqtt_settings` | Broker und Auto-Discovery |
| `message_settings` | Zeitverhalten der UDP-Kommunikation |
| `additions_status_requests` | optionale Abfrage und Startwerte |
| `passiv_mode_settings` | Grenzen und Startwerte des Passive-Modus |
| `general_settings` | Watchdog und Betrieb |
| `logging` | Log-Level |

Home Assistant zeigt Name und Beschreibung nur je **Gruppe** an
(`translations/de.yaml`, `translations/en.yaml`); die Felder darunter erscheinen
mit ihrem Schluesselnamen. Diese Seite ist die ausfuehrliche Referenz je Feld.

## Gerät

| Option | Default | Beschreibung |
|---|---|---|
| `device_ip` | `192.168.0.45` | IP des Speichers. Statische IP bzw. DHCP-Reservierung empfohlen. |
| `device_udp_port` | `30000` | In der Marstek-App gesetzter UDP-Port. |
| `device_ble_mac` | *(leer)* | Wird nach dem ersten `Marstek.GetDevice` automatisch befüllt und zurückgeschrieben. |
| `device_type` | *(leer)* | Ebenso - z. B. `VenusC`. Wird als Modell in HA verwendet. |
| `local_udp_port` | `0` | Lokaler Quellport. `0` = zufällig. Einzelne Firmware-Stände antworten nur auf feste Ports - dann hier z. B. `30000` eintragen. |

Die ausgelesenen Werte landen in `/data/marstek_state.json` und - wenn
`persist_device_info` aktiv ist - zusätzlich über die Supervisor-API in den
Add-on-Optionen (dafür ist `hassio_role: manager` gesetzt).

## MQTT

| Option | Default |
|---|---|
| `mqtt_host` | `core-mosquitto` |
| `mqtt_port` | `1883` |
| `mqtt_username` / `mqtt_password` | `mqtt-marstek` |
| `mqtt_discovery_prefix` | `homeassistant` |
| `mqtt_base_topic` | `Marstek-Bridge-Control` |
| `mqtt_suggested_area` | `Marstek` |

Leerer Benutzername = anonyme Verbindung.

## Kommunikation

| Option | Default | Beschreibung |
|---|---|---|
| `request_delay` | `1.0` | Pause zwischen zwei Abfragen in Sekunden. |
| `request_timeout` | `1.0` | Timeout je Versuch. |
| `request_retries` | `2` | `0` = kein Retry, Nachricht wird verworfen und löst **keinen** Watchdog aus. `>0` = Wiederholungen, bei endgültigem Fehlschlag Watchdog. |
| `request_max_time` | `10.0` | Hartes Limit über alle Versuche einer Nachricht. Wird es überschritten, greift der Watchdog (Sonderfall). |
| `poll_interval` | `30` | Sekunden zwischen zwei Polling-Zyklen. |
| `poll_enabled` | `true` | Polling abschaltbar (dann nur Refresh-Button). |
| `enable_em` | `false` | Zusätzlich `EM.GetStatus` abfragen → Gerät *Marstek Energy Meter*. |

**Message-IDs:** Jede gesendete Nachricht bekommt eine eigene laufende `id`
(0 → 999 → 0). Antworten mit fremder `id` werden verworfen.

**Instance-IDs:** Jede Methode nutzt eine eigene `params.id` (siehe
`app/const.py`, `INSTANCE_IDS`): GetDevice 0, Wifi 1, BLE 2, Bat 3, PV 4,
ES.GetStatus 5, ES.GetMode 6, ES.SetMode 7, EM 8, DOD 9, Ble.Adv 10, Led 11.

## Initialwerte

| Option | Default | Beschreibung |
|---|---|---|
| `dod_value` | `88` | Depth of Discharge, Bereich 30-88. |
| `ble_block_enable` | `true` | Bluetooth-Sperre beim Start aktivieren. Gesendet wird `Ble.Adv {"enable": 0}` (Doku 3.9: 0 = enable). |
| `led_state` | `false` | LED des Bedienpanels beim Start ausschalten. |

## Passive-Modus

| Option | Default | Beschreibung |
|---|---|---|
| `passive_power_min` | `-1200` | Untere Grenze (Laden). |
| `passive_power_max` | `1200` | Obere Grenze (Einspeisen). |
| `passive_power_default` | `0` | Startwert der Number-Entity. |
| `passive_cd_time_max` | `300` | Maximaler Countdown in Sekunden. |
| `passive_cd_time_default` | `10` | Startwert des Countdowns. |
| `passive_keepalive` | `false` | Sendet den Passive-Befehl automatisch alle `cd_time/2` Sekunden erneut, solange Passive aktiv ist. Bei aktiver Selbstregelung passiert das ohnehin immer. |
| `self_regulation_enabled` | `false` | Startzustand der Selbstregelung (auch als Switch in HA). |
| `self_regulation_topic` | *(leer)* | Topic des gefilterten Regelwerts. Leer = `<mqtt_base_topic>/energy_control/regulation_input`. |
| `self_regulation_mode` | `setpoint` | `setpoint` = Wert ist der fertige Sollwert und wird direkt übernommen. `grid` = Wert ist die Netzleistung und wird auf den bisherigen Sollwert aufsummiert. |
| `self_regulation_reserve` | `12` | Reserve in Watt, die abgezogen wird, damit der Netzbezug leicht positiv bleibt. |
| `self_regulation_deadband` | `10` | Änderungen kleiner als dieser Wert lösen kein neues Kommando aus. |
| `self_regulation_min_interval` | `2.0` | Minimaler Abstand zwischen zwei Regelbefehlen in Sekunden. |

## Betrieb

| Option | Default | Beschreibung |
|---|---|---|
| `watchdog_failure_threshold` | `3` | Anzahl aufeinanderfolgender Watchdog-Auslösungen, bis `/health` 503 liefert (verhindert Neustart-Schleifen bei kurzen Aussetzern). |
| `persist_device_info` | `true` | `device_ble_mac`/`device_type` in die Add-on-Optionen zurückschreiben. |
| `health_port` | `8099` | Port des Health-Endpoints (muss zum `watchdog:`-Eintrag passen). |
| `log_level` | `info` | `trace` \| `debug` \| `info` \| `warning` \| `error`. `trace` loggt jedes UDP- und MQTT-Paket. |
| `log_full_line_color` | `true` | Ein: die komplette Zeile erscheint in der Levelfarbe (grau/cyan/grün/gelb/rot). Aus: nur Zeitstempel, Level und Logger-Name sind farbige Akzente. |

## Selbstregelung im Passive-Modus

Die Bridge lauscht auf einem Topic mit dem gefilterten Regelwert und leitet
daraus die Leistung des Passive-Kommandos ab.

```
Ausgang = clamp( f(Regelwert) - Reserve , 0 , "Passive power" )
```

* **Obergrenze** ist die Number-Entity *Passive power*. Ohne Selbstregelung ist
  sie der direkte Sollwert, mit Selbstregelung nur noch der Deckel. Steht sie
  auf 300 W, werden aus einem Regelwert von 400 W trotzdem nur 300 W.
* **Untergrenze** ist fest 0 W. Der Ausgang wird nie negativ, es wird also
  weder ins Netz eingespeist noch aus dem Netz geladen.
* **Reserve** (`self_regulation_reserve`, Standard 12 W) wird abgezogen, damit
  der Netzbezug leicht im positiven Bereich bleibt statt auf 0 zu kippen.
* **Modus** (`self_regulation_mode`):
  * `setpoint` - der empfangene Wert ist bereits der gewünschte Sollwert des
    Speichers (z. B. in HA aus Last minus PV gerechnet) und wird direkt
    übernommen.
  * `grid` - der empfangene Wert ist die Netzleistung (Bezug positiv). Der neue
    Sollwert ist `alter Sollwert + Netzwert - Reserve`. Diese Variante regelt
    sich selbst ein und ist die richtige Wahl, wenn der Wert direkt vom
    Zähler kommt.
* **Kein neuer Wert?** Der Keepalive sendet den zuletzt berechneten Wert alle
  `cd_time/2` Sekunden erneut und startet damit den Countdown des Geräts neu.
  Bei aktiver Selbstregelung läuft er unabhängig von `passive_keepalive`.
* **Voraussetzung:** Der Modus *Passive* muss über Select und Apply-Button
  aktiv sein. Solange ein anderer Modus läuft, wird der Regelwert nur
  gespeichert und angezeigt.

Payload-Formate: eine reine Zahl (`415` oder `415.7`) oder JSON mit einem der
Schlüssel `value`, `state`, `power`, `p`.

Beispiel-Automation, die einen gefilterten Sensor weiterreicht:

```yaml
- trigger:
    - platform: state
      entity_id: sensor.grid_power_filtered
  action:
    - service: mqtt.publish
      data:
        topic: Marstek-Bridge-Control/energy_control/regulation_input
        payload: "{{ states('sensor.grid_power_filtered') }}"
```

Neue Entities im Gerät *Marstek Energy Control*: Switch **Self-regulation**,
Sensor **Regulation input** (zuletzt empfangen) und Sensor **Regulation output**
(zuletzt gesendet).

## MQTT-Topics

```
Marstek-Bridge-Control/status                       online | offline
Marstek-Bridge-Control/system/state                 JSON
Marstek-Bridge-Control/battery/state                JSON
Marstek-Bridge-Control/pv/state                     JSON
Marstek-Bridge-Control/energy_status/state          JSON
Marstek-Bridge-Control/energy_mode/state            JSON
Marstek-Bridge-Control/energy_control/state         JSON
Marstek-Bridge-Control/energy_meter/state           JSON

Marstek-Bridge-Control/system/dod/set                     30..88
Marstek-Bridge-Control/system/ble_block/set               ON | OFF
Marstek-Bridge-Control/system/led/set                     ON | OFF
Marstek-Bridge-Control/energy_control/mode/set            Auto|AI|Passive|UPS
Marstek-Bridge-Control/energy_control/passive_power/set   W
Marstek-Bridge-Control/energy_control/passive_cd_time/set s
Marstek-Bridge-Control/energy_control/self_regulation/set ON | OFF
Marstek-Bridge-Control/energy_control/regulation_input    W  (Regelwert, konfigurierbar)
Marstek-Bridge-Control/energy_control/apply/set           PRESS
Marstek-Bridge-Control/energy_control/refresh/set         PRESS  (alle Gruppen)
Marstek-Bridge-Control/battery/refresh/set                PRESS  (nur Bat.GetStatus)
Marstek-Bridge-Control/pv/refresh/set                     PRESS  (nur PV.GetStatus)
Marstek-Bridge-Control/energy_status/refresh/set          PRESS  (nur ES.GetStatus)
Marstek-Bridge-Control/energy_mode/refresh/set            PRESS  (nur ES.GetMode)
Marstek-Bridge-Control/energy_meter/refresh/set           PRESS  (nur EM.GetStatus)
```

## Hinweise

* Der UPS-Modus wird fest als `"UPS"` gesendet (wie im Doku-Beispiel), auch
  wenn die Modus-Liste im Text `Ups` schreibt.

* `Manual` ist absichtlich nicht im Select: der Modus braucht Zeitfenster
  (`time_num`, `start_time`, `end_time`, `week_set`) und folgt später.
* `input_energy` / `output_energy` werden laut Doku mit 0,1 multipliziert und
  als Wh veröffentlicht.
* Das Aktivieren der Open API kann gerätintern Funktionen deaktivieren, um
  Befehlskonflikte zu vermeiden (siehe Marstek-Doku, Kapitel 2).

## Kommunikationsstatus in Automationen

| Entity | Zustaende | geeignet fuer |
|---|---|---|
| `sensor.<...>_system_communication` - *Communication established* | `ON` / `FAIL` | Anzeige, Benachrichtigungstext |
| `binary_sensor.<...>_system_comm_ok` - *Device connectivity* | `on` / `off` (`device_class: connectivity`) | Bedingungen und Trigger in Automationen |

```yaml
# Benachrichtigen, sobald der Speicher nicht mehr antwortet
triggers:
  - trigger: state
    entity_id: binary_sensor.marstek_..._system_comm_ok
    to: "off"
    for: "00:02:00"
```

## Fehlersuche

| Symptom | Ursache / Lösung |
|---|---|
| Keine Antwort auf UDP | Open API in der App aktiv? Port korrekt? Gleiches Subnetz? `local_udp_port` auf den Geräteport setzen. |
| Entities „unavailable" | Add-on gestoppt oder MQTT getrennt - Log prüfen. |
| *Communication established* = FAIL | Speicher antwortet nicht; `request_timeout`/`request_retries` erhöhen. |
| Add-on startet ständig neu | Watchdog greift; `watchdog_failure_threshold` erhöhen oder Watchdog deaktivieren. |
| `set_result` false | Modus/Parameter vom Modell nicht unterstützt (Doku Kapitel 4). |
