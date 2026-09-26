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
| `pv_energy_enabled` | `true` | Eigener PV-Energiezähler (Integral über `pv_power`). |
| `pv_energy_max_gap` | `300` | Größte Lücke in Sekunden zwischen zwei Messwerten, die noch hochgerechnet wird. |

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
| `self_regulation_topic` | *(leer)* | Topic des Regelwerts (Netzleistung, Bezug positiv). Leer = `<mqtt_base_topic>/energy_control/regulation_input`. |
| `self_regulation_reserve` | `12` | Ziel-Netzbezug in Watt, auf den geregelt wird. |
| `self_regulation_deadband` | `10` | Abweichungen darunter lösen kein Kommando aus (nur beim Hochregeln). |
| `self_regulation_min_interval` | `5.0` | Minimaler Abstand zwischen zwei Regelbefehlen (nur beim Hochregeln). |
| `self_regulation_step_gain` | `0.5` | Anteil der Abweichung pro Schritt nach oben. |
| `self_regulation_step_up` | `50` | Harte Obergrenze eines Schritts nach oben in Watt. |
| `self_regulation_step_down` | `0` | Begrenzung nach unten in Watt, `0` = unbegrenzt. |
| `self_regulation_fast_down` | `true` | Runterregeln überspringt Totband und Mindestabstand. |
| `self_regulation_input_timeout` | `60` | Sekunden ohne Wert bis Rückfall auf 0 W, `0` = aus. |

## Betrieb

| Option | Default | Beschreibung |
|---|---|---|
| `watchdog_failure_threshold` | `3` | Anzahl aufeinanderfolgender Watchdog-Auslösungen, bis `/health` 503 liefert (verhindert Neustart-Schleifen bei kurzen Aussetzern). |
| `persist_device_info` | `true` | `device_ble_mac`/`device_type` in die Add-on-Optionen zurückschreiben. |
| `health_port` | `8099` | Port des Health-Endpoints (muss zum `watchdog:`-Eintrag passen). |
| `log_level` | `info` | `trace` \| `debug` \| `info` \| `warning` \| `error`. `trace` loggt jedes UDP- und MQTT-Paket. |
| `log_full_line_color` | `true` | Ein: die komplette Zeile erscheint in der Levelfarbe (grau/cyan/grün/gelb/rot). Aus: nur Zeitstempel, Level und Logger-Name sind farbige Akzente. |

## Selbstregelung im Passive-Modus

Die Bridge erwartet auf `self_regulation_topic` die **Netzleistung** (Bezug
positiv, Einspeisung negativ) und regelt sie auf `self_regulation_reserve`
ein - typisch 10-15 W, damit der Bezug nie ins Negative kippt.

```
Abweichung = Netzwert − Reserve

Abweichung > 0  (zu viel Bezug)   → Schritt = min(Abweichung × step_gain, step_up)
Abweichung < 0  (zu wenig Bezug)  → Schritt = Abweichung   (voll, ungebremst)

Sollwert = clamp(Sollwert + Schritt, 0, "Passive power")
```

Die Regelung ist bewusst **asymmetrisch**: Hochregeln kann überschießen und
damit Einspeisung verursachen, Runterregeln ist immer die sichere Richtung.

* **Nach oben gebremst.** Pro Schritt wird nur `step_gain` (Standard 0,5) der
  Abweichung ausgeglichen, höchstens aber `step_up` Watt. Der Regler nähert
  sich dem Ziel an, statt darüber hinauszuschießen.
* **Nach unten sofort.** Der volle Betrag wird in einem Schritt korrigiert. Ein
  Lastabfall von 500 auf 50 W zieht den Sollwert in einem Zug herunter.
* **Fast-Down.** Mit `self_regulation_fast_down` überspringt ein Schritt nach
  unten sowohl Totband als auch Mindestabstand - sonst würde nach einem
  Lastabfall bis zu `min_interval` Sekunden lang zu viel eingespeist.
* **Obergrenze** ist die Number-Entity *Passive power*. Ohne Selbstregelung ist
  sie der direkte Sollwert, mit Selbstregelung nur noch der Deckel.
* **Untergrenze** ist fest 0 W. Der Sollwert wird nie negativ, es wird also
  weder ins Netz eingespeist noch aus dem Netz geladen.
* **Kein Windup:** Basis jedes Schritts ist der bereits begrenzte Sollwert, der
  Regler kann sich nicht über den Deckel hinaus aufsummieren.
* **Kein neuer Wert?** Der Keepalive sendet den aktuellen Sollwert alle
  `cd_time/2` Sekunden erneut und startet damit den Countdown des Geräts neu.
  Bleiben Werte länger als `self_regulation_input_timeout` aus (HA-Neustart,
  Automation deaktiviert, Sensor tot), fällt der Sollwert auf 0 W.
* **Voraussetzung:** Der Modus *Passive* muss über Select und Apply-Button
  aktiv sein. Solange ein anderer Modus läuft, wird der Regelwert nur
  gespeichert und angezeigt.

Beispiel mit Reserve 12 W, Deckel 600 W, Standardparametern:

| Netz | Sollwert alt | | Sollwert neu |
|---|---|---|---|
| 512 W | 0 | halbe Abweichung, gedeckelt auf 50 | 50 W |
| 512 W | 50 | ebenso | 100 W |
| … | … | neun Schritte à 50 W | 450 W |
| 62 W | 450 | halbe Abweichung = 25 | 475 W |
| 12 W | 497 | Ziel erreicht | 497 W |
| −450 W | 497 | voller Betrag, sofort | 35 W |

Payload-Formate: eine reine Zahl (`415` oder `415.7`) oder JSON mit einem der
Schlüssel `value`, `state`, `power`, `p`.

Beispiel-Automation:

```yaml
alias: Publish MQTT Marstek Regelwert
triggers:
  - trigger: state
    entity_id: sensor.phase_c_average
  - trigger: time_pattern
    seconds: /5
conditions:
  - condition: template
    value_template: >-
      {{ states('sensor.phase_c_average') not in
         ['unknown', 'unavailable', 'none', ''] }}
  - condition: state
    entity_id: sensor.marstek_..._system_communication
    state: "ON"
actions:
  - action: mqtt.publish
    data:
      topic: marstek/average_phaseC
      payload: "{{ states('sensor.phase_c_average') | float(0) | round(0) }}"
      qos: 0
      retain: false
mode: single
```

Zur Glättung der Quelle: Ein kurzes Mittel (etwa 5 Sekunden) reicht, weil die
Bridge nach oben ohnehin dämpft. Ein längeres Fenster verzögert nur die
Reaktion auf Lastabfälle, also genau das, was schnell gehen soll.

Neue Entities im Gerät *Marstek Energy Control*: Switch **Self-regulation**,
Sensor **Regulation input** (zuletzt empfangen) und Sensor **Regulation output**
(zuletzt gesendet).

## Eigener PV-Energiezähler

Der Zähler `total_pv_energy` des Geräts ist unzuverlässig, `pv_power` dagegen
korrekt. Die Bridge integriert deshalb bei jeder `ES.GetStatus`-Antwort selbst:

```
Wh += (P_vorher + P_jetzt) / 2 × Δt / 3600
```

* **Trapezregel** statt Rechteck, weil die Abfrage nicht in exakt gleichen
  Abständen kommt (Refresh-Button, HA-gesteuertes Polling).
* **Δt ist die tatsächlich vergangene Zeit** zwischen zwei Antworten, kein
  angenommenes Intervall.
* **Lücken** größer als `pv_energy_max_gap` (Standard 300 s) werden verworfen
  und mit einer Warnung im Log vermerkt. Der Zähler bleibt dabei stehen, zählt
  ab dem nächsten Wert aber normal weiter.
* **Nach einem Neustart** wird der Zählerstand aus `/data/marstek_state.json`
  übernommen; der erste Messwert dient nur als Stützstelle, die Ausfallzeit
  wird also nicht mitgezählt.

Die Entity heißt **PV energy (calculated)** und liegt im Gerät *Marstek Energy
Status*. Sie ist `device_class: energy` mit `state_class: total_increasing` und
kann direkt im Energie-Dashboard als Solarproduktion eingebunden werden.

Zum Zurücksetzen das Add-on stoppen, in `/data/marstek_state.json` den
Schlüssel `pv_energy_wh` löschen oder auf den gewünschten Wert setzen und das
Add-on wieder starten.

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
