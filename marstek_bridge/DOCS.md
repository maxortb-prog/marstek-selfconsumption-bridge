# Marstek Self-consumption Bridge - Konfiguration

Alle Optionen sind in der Add-on-Oberflaeche mit Namen und Beschreibung
hinterlegt (`translations/de.yaml`, `translations/en.yaml`). Diese Seite ist
die ausfuehrliche Referenz dazu.

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
| `passive_keepalive` | `false` | Sendet den Passive-Befehl automatisch alle `cd_time/2` Sekunden erneut, solange Passive aktiv ist. |

## Betrieb

| Option | Default | Beschreibung |
|---|---|---|
| `watchdog_failure_threshold` | `3` | Anzahl aufeinanderfolgender Watchdog-Auslösungen, bis `/health` 503 liefert (verhindert Neustart-Schleifen bei kurzen Aussetzern). |
| `persist_device_info` | `true` | `device_ble_mac`/`device_type` in die Add-on-Optionen zurückschreiben. |
| `health_port` | `8099` | Port des Health-Endpoints (muss zum `watchdog:`-Eintrag passen). |
| `log_level` | `info` | `trace` \| `debug` \| `info` \| `warning` \| `error`. `trace` loggt jedes UDP- und MQTT-Paket. Alle Level werden farbig (ANSI) ausgegeben. |

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

## Fehlersuche

| Symptom | Ursache / Lösung |
|---|---|
| Keine Antwort auf UDP | Open API in der App aktiv? Port korrekt? Gleiches Subnetz? `local_udp_port` auf den Geräteport setzen. |
| Entities „unavailable" | Add-on gestoppt oder MQTT getrennt - Log prüfen. |
| *Communication established* = FAIL | Speicher antwortet nicht; `request_timeout`/`request_retries` erhöhen. |
| Add-on startet ständig neu | Watchdog greift; `watchdog_failure_threshold` erhöhen oder Watchdog deaktivieren. |
| `set_result` false | Modus/Parameter vom Modell nicht unterstützt (Doku Kapitel 4). |
