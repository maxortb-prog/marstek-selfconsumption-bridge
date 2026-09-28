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
| `request_delay` | `1.0` | **Mindestpause zwischen allen UDP-Anfragen** - Polling, Regelkommandos, Keepalive und Refresh-Buttons. |
| `request_timeout` | `1.0` | Timeout je Versuch. |
| `request_retries` | `2` | `0` = kein Retry, Nachricht wird verworfen und löst **keinen** Watchdog aus. `>0` = Wiederholungen, bei endgültigem Fehlschlag Watchdog. |
| `request_max_time` | `10.0` | Hartes Limit über alle Versuche einer Nachricht. Wird es überschritten, greift der Watchdog (Sonderfall). |
| `poll_enabled` | `true` | Hauptschalter für das zyklische Polling. |
| `poll_quiet_after_write` | `3.0` | Ruhezeit nach einem Schreibkommando, in der keine Statusabfrage startet. |
| `poll_interval_es_status` | `10` | `ES.GetStatus` - die laufenden Leistungswerte. |
| `poll_interval_battery` | `300` | `Bat.GetStatus` - vor allem die Temperatur. |
| `poll_interval_pv` | `0` | `PV.GetStatus` - aus, steckt in Teilen in `ES.GetStatus`. |
| `poll_interval_mode` | `0` | `ES.GetMode` - aus, nach dem Start meist unverändert. |
| `poll_interval_em` | `0` | `EM.GetStatus` - aus. |
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
| `self_regulation_reserve` | `12` | Obere Kante des Haltebands und Ziel jeder Korrektur. |
| `self_regulation_band_low` | `0` | Untere Kante des Haltebands. Darunter wird zurückgeregelt. |
| `self_regulation_deadband` | `10` | Abweichung des **Netzwerts** ab der Reserve, unter der nicht geregelt wird (nur beim Hochregeln). |
| `self_regulation_min_interval` | `5.0` | Minimaler Abstand zwischen zwei Regelbefehlen (nur beim Hochregeln). |
| `self_regulation_min_interval_down` | `5.0` | Minimaler Abstand beim Runterregeln. |
| `self_regulation_settle_time` | `10.0` | Totzeit, über die eine gesendete Änderung als „in der Messung noch nicht sichtbar" gilt. `0` = aus. |
| `self_regulation_step_gain` | `0.5` | Anteil der Abweichung pro Schritt nach oben. |
| `self_regulation_step_up` | `50` | Harte Obergrenze eines Schritts nach oben in Watt. |
| `self_regulation_step_down` | `0` | Begrenzung nach unten in Watt, `0` = unbegrenzt. |
| `self_regulation_fast_down` | `true` | Runterregeln überspringt Totband und Mindestabstand. |
| `self_regulation_input_timeout` | `60` | Sekunden ohne Wert bis Rückfall auf 0 W, `0` = aus. |

## Betrieb

| Option | Default | Beschreibung |
|---|---|---|
| `restore_state` | `true` | Steuerzustand über Neustarts hinweg sichern und wiederherstellen. |
| `watchdog_failure_threshold` | `3` | Anzahl aufeinanderfolgender Watchdog-Auslösungen bzw. gescheiterter Init-Versuche, bis `/health` 503 liefert. |
| `persist_device_info` | `true` | `device_ble_mac`/`device_type` in die Add-on-Optionen zurückschreiben. |
| `health_port` | `8099` | Port des Health-Endpoints (muss zum `watchdog:`-Eintrag passen). |
| `log_level` | `info` | `trace` \| `debug` \| `calc` \| `info` \| `warning` \| `error`. Siehe unten. |
| `log_full_line_color` | `true` | Ein: die komplette Zeile erscheint in der Levelfarbe (grau/cyan/grün/gelb/rot). Aus: nur Zeitstempel, Level und Logger-Name sind farbige Akzente. |

## Selbstregelung im Passive-Modus

Die Bridge erwartet auf `self_regulation_topic` die **Netzleistung** (Bezug
positiv, Einspeisung negativ) und regelt sie auf `self_regulation_reserve`
ein - typisch 10-15 W, damit der Bezug nie ins Negative kippt.

```
Messwert = Netzwert − Δ_unsichtbar

Messwert > Reserve      → Abweichung = Messwert − Reserve   hoch, gebremst
band_low ≤ M ≤ Reserve  → Abweichung = 0                    Halteband, nichts
Messwert < band_low     → Abweichung = Messwert − Reserve   runter, voll

Schritt hoch   = min(Abweichung × step_gain, step_up)
Schritt runter = Abweichung
Sollwert = clamp(Sollwert + Schritt, 0, "Passive power")
```

Die Regelung ist bewusst **asymmetrisch**: Hochregeln kann überschießen und
damit Einspeisung verursachen, Runterregeln ist immer die sichere Richtung.

* **Halteband** zwischen `band_low` (Standard 0 W) und `reserve`. Liegt der
  Netzbezug darin, passiert nichts. Ein Bezug von 4 W ist besser als die
  Reserve von 10 W - dafür Speicherleistung zurückzunehmen wäre verschenkt.
  Korrigiert wird erst, wenn der Wert das Band verlässt, und dann immer zurück
  auf die Reserve: bei −20 W also um 30 W. Bis exakt 0 W zurückzuregeln würde
  den Arbeitspunkt an die Kante legen, wo ihn das nächste Messrauschen wieder
  ins Negative kippt.

* **Nach oben gebremst.** Pro Schritt wird nur `step_gain` (Standard 0,5) der
  Abweichung ausgeglichen, höchstens aber `step_up` Watt. Der Regler nähert
  sich dem Ziel an, statt darüber hinauszuschießen.
* **Nach unten sofort.** Der volle Betrag wird in einem Schritt korrigiert. Ein
  Lastabfall von 500 auf 50 W zieht den Sollwert in einem Zug herunter.
* **Fast-Down.** Mit `self_regulation_fast_down` überspringt ein Schritt nach
  unten sowohl Totband als auch Mindestabstand - sonst würde nach einem
  Lastabfall bis zu `min_interval` Sekunden lang zu viel eingespeist.
* **Obergrenze** ist die Number-Entity *Passive power*. Ohne Selbstregelung ist
  sie der direkte Sollwert, mit Selbstregelung nur noch der Deckel. Sie lässt
  sich im laufenden Betrieb verändern, etwa SOC-abhängig aus einer
  HA-Automation.
* **Ein gesenkter Deckel wirkt sofort.** Liegt der aktuelle Sollwert darüber,
  wird er im selben Moment gekappt und gesendet - ohne Rücksicht auf Totband
  und Mindestabstand, denn Absenken ist immer die sichere Richtung. Zusätzlich
  prüft jedes ausgehende Kommando den Sollwert gegen den aktuellen Deckel, auch
  das des Keepalives. Ein angehobener Deckel wird beim nächsten regulären
  Regelschritt genutzt.
* **Das Totband gilt für den Netzwert, nicht für den Sollwert.** Die Schwelle
  ist `reserve + deadband`: bei Reserve 8 W und Totband 5 W wird ab 13 W
  Netzbezug nachgeregelt. Würde das Totband auf den berechneten Sollwert
  wirken, hinge seine Wirkung an `step_gain` - bei `gain 0.5` entspräche ein
  Totband von 5 W am Ausgang einer Abweichung von 10 W am Eingang.
* **Ändert sich der Sollwert nicht**, wird nichts gesendet - etwa wenn er
  bereits am Deckel steht.
* **Untergrenze** ist fest 0 W. Der Sollwert wird nie negativ, es wird also
  weder ins Netz eingespeist noch aus dem Netz geladen.
* **Kein Windup:** Basis jedes Schritts ist der bereits begrenzte Sollwert, der
  Regler kann sich nicht über den Deckel hinaus aufsummieren.
* **Totzeit-Kompensation.** Zwischen Kommando und Messwert vergeht Zeit: der
  Speicher braucht einen Moment, ein gemittelter Sensor deutlich länger. Ohne
  Korrektur sieht der Regler seine eigene, gerade abgeschickte Änderung noch
  nicht und regelt denselben Fehler mehrfach aus - das Ergebnis ist ein
  massives Überschießen und anschließendes Schwingen. Die Bridge merkt sich
  deshalb die zuletzt befohlene Änderung Δ und zieht den noch nicht sichtbaren
  Anteil vom Fehler ab. Er verfällt linear über `self_regulation_settle_time`.
  Richtwert für diese Zeit: Reaktionszeit des Speichers plus Mittelungsfenster
  des Sensors, typisch 10-20 Sekunden. **`settle_time` sollte nicht größer sein
  als `min_interval`** - sonst überlagern sich zwei aufeinanderfolgende
  Kommandos in der Kompensation und der Regler korrigiert zu stark nach unten.
  Die Bridge warnt beim Start, wenn das der Fall ist.
* **Takt nach unten.** Auch ein Fast-Down hält `min_interval_down` (Standard
  5 s) ein. Übersprungen werden nur das Totband und der längere
  Aufwärts-Takt.
* **Kein neuer Wert?** Der Keepalive sendet den aktuellen Sollwert alle
  `cd_time/2` Sekunden erneut und startet damit den Countdown des Geräts neu.
  Bleiben Werte länger als `self_regulation_input_timeout` aus (HA-Neustart,
  Automation deaktiviert, Sensor tot), fällt der Sollwert auf 0 W.
* **Voraussetzung:** Der Modus *Passive* muss über Select und Apply-Button
  aktiv sein. Solange ein anderer Modus läuft, wird der Regelwert nur
  gespeichert und angezeigt. Danach ist ein erneutes Apply weder nötig noch
  wirksam - der Keepalive hält den Modus am Leben, und ein Apply von außen
  würde nur einen veralteten Sollwert dazwischenschieben.

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

### Log-Level

| Level | Zeigt |
|---|---|
| `error` / `warning` | nur Probleme |
| `info` | Ablauf: Init, Modus-Wechsel, jede empfangene MQTT-Regelnachricht |
| `calc` | zusätzlich alle **Rechenwege**: Regelschritte mit Totzeit-Korrektur, Keepalive, Totband- und Deckel-Eingriffe, automatische `ES.SetMode`-Kommandos, PV-Energiezähler |
| `debug` | zusätzlich jede UDP-Abfrage und jedes MQTT-Kommando |
| `trace` | zusätzlich jedes einzelne UDP- und MQTT-Paket im Klartext |

`calc` ist die Stufe zum Nachvollziehen der Regelung, ohne sich das
Protokoll-Rauschen einzuhandeln. Eine Zeile pro Regelschritt sieht so aus:

```
CALC  Rechnung: Netz 21.0 W - Totzeit 8.0 W = 13.0 W | Band 0-10 W |
      Abweichung +3.0 W | Schritt +1.5 W (hoch, gain 0.5 / max 50 W) |
      17 -> 19 W | Deckel 180 W
CALC  Selbstregelung hoch: 17 W -> 19 W wird gesendet
CALC  Passive-Keepalive: 19 W erneut gesendet (cd_time=30s)
```

Damit ist jeder Schritt nachrechenbar: gemessener Wert, abgezogene Totzeit,
Lage zum Halteband, Größe und Begründung des Schritts, alter und neuer Sollwert.

### Was im Log steht

Auf Level `info` erzeugt jede empfangene MQTT-Nachricht genau eine Zeile:

```
MQTT-Regelwert 512.0 W (Ziel 12 W) | Sollwert 0 W -> 50 W | Deckel 600 W
MQTT-Regelwert -200.0 W (Ziel 12 W) | Sollwert 150 W -> 0 W | Deckel 600 W
MQTT-Regelwert 300.0 W - Passive-Modus ist nicht aktiv, kein Kommando
MQTT-Regelwert 300.0 W - Selbstregelung ist aus
```

Der gezeigte Sollwert ist der aus diesem Wert berechnete. Ob er auch gesendet
wird, entscheiden Totband und Mindestabstand - das steht auf Level `debug`,
ebenso das eigentliche `ES.SetMode`, der Fast-Down-Hinweis und der Keepalive.
Bleibt der Sollwert über mehrere Zeilen gleich, wurde dazwischen wegen des
Mindestabstands noch nicht gesendet.

## Verhalten nach einem Neustart

Mit `restore_state` (Standard aktiv) nimmt die Bridge den Betrieb dort wieder
auf, wo sie aufgehört hat, statt bei 0 W zu beginnen.

Gesichert werden in `/data/marstek_state.json` unter dem Schlüssel `control`:
der Deckel *Passive power*, der Countdown, der Schalter *Self-regulation*, der
vorgemerkte Modus und der zuletzt berechnete Sollwert. Geschrieben wird bei
jeder Änderung.

Der Startwert der Regelung wird beim ersten `ES.GetMode` bestimmt:

| Meldung des Geräts | Startwert |
|---|---|
| Modus `Passive`, `ongrid_power` > 0 | die gemessene Leistung des Geräts, auf den Deckel begrenzt |
| anderer Modus (Countdown abgelaufen) | der gesicherte Sollwert, auf den Deckel begrenzt |
| nichts gesichert | 0 W |

Der Gerätewert hat Vorrang, weil er die tatsächliche Lage abbildet - der
Speicher kann während der Ausfallzeit weitergelaufen sein. Verlässt er den
Passive-Modus, weil der Countdown abgelaufen ist, ist seine Meldung
bedeutungslos und der gesicherte Wert die bessere Auskunft.

Der zuletzt *aktive* Modus wird bewusst nicht wiederhergestellt: Ob das Gerät
noch im Passive-Modus steht, weiß erst `ES.GetMode`. Die Regelung sendet
deshalb erst wieder, wenn der Modus über Select und Apply aktiv ist.

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

## Polling

Jede Abfrage hat ihr eigenes Intervall in Sekunden, `0` schaltet sie ab. Der
Grund: Die Abfragen sind sehr unterschiedlich ergiebig. `ES.GetStatus` trägt
die laufenden Leistungswerte und lohnt oft, `Bat.GetStatus` liefert vor allem
die Temperatur und reicht alle paar Minuten, `ES.GetMode` ändert sich nach dem
Start kaum, und `PV.GetStatus` ist nur interessant, wenn die einzelnen Strings
zählen - die Summe steckt schon in `ES.GetStatus`.

Pro Schleifendurchlauf wird höchstens **eine** fällige Abfrage ausgeführt, der
Rest folgt im nächsten Durchlauf. So drücken gleichzeitig fällige Intervalle
nicht mehrere Anfragen auf einmal heraus.

Der Button *Refresh data* im Gerät *Marstek Energy Control* fragt weiterhin
alle Gruppen auf einmal ab, unabhängig von den Intervallen.

Der Button *Apply mode* liest den Modus nach dem Umschalten nach, damit die
Gruppe *Marstek Energy Mode* den neuen Zustand zeigt - aber nur, wenn
`poll_interval_mode` größer 0 ist. Läuft der Passive-Modus bereits **und** ist
die Selbstregelung aktiv, sendet der Button gar nichts mehr: Zeitpunkt und
Leistung bestimmt dann die Regelschleife samt Keepalive. Der zuletzt empfangene
Regelwert wird lediglich für den nächsten Durchlauf vorgemerkt. Sonst löst eine Automation, die zyklisch auf
Apply drückt, bei jedem Druck ein zusätzliches `ES.GetMode` aus.

### Ruhezeit nach Schreibkommandos

Direkt nach einem `ES.SetMode` ist der Speicher einige Sekunden beschäftigt und
lässt Statusabfragen in den Timeout laufen, obwohl er erreichbar ist.
`poll_quiet_after_write` (Standard 3 s) hält in dieser Zeit alle Abfragen
zurück - Polling ebenso wie die Refresh-Buttons.

Bei laufender Selbstregelung landen die Abfragen damit im Fenster zwischen zwei
Regelkommandos. Damit eine Abfrage bei dichtem Regeltakt nicht dauerhaft
verschoben wird, läuft sie trotzdem, sobald sie das Doppelte ihres Intervalls
überfällig ist.

### Mindestpause zwischen Anfragen

`request_delay` gilt seit 0.0.21 für **alle** UDP-Anfragen, nicht mehr nur
zwischen Polling-Schritten. Der UDP-Client merkt sich, wann er zuletzt gesendet
hat, und wartet vor jeder Anfrage, bis die Pause um ist - egal ob sie vom
Polling, von der Regelung, vom Keepalive oder von einem Refresh-Button kommt.

Ohne das kollidieren Abfragen mit Regelkommandos: Der Speicher antwortet dann
erst nach mehreren Sekunden, die Anfrage ist längst im Timeout, und die
verspätete Antwort taucht als *„Ignoriere Antwort mit fremder id"* auf.
Verspätete Antworten werden jetzt zusätzlich vor jeder neuen Anfrage aus dem
Puffer geworfen.

Der Preis: Ein Regelkommando kann sich um bis zu `request_delay` verzögern.

## Abbruch der Initialisierung

Der Speicher schließt seinen UDP-Port, wenn im Passive-Modus keine Kommandos
mehr eintreffen, und meldet sich erst nach Ablauf seines Countdowns zurück -
dann meist im Auto-Modus. Genau das passiert bei einem Neustart der Bridge.

Läuft deshalb ein Schritt der Init-Sequenz in einen Timeout, bricht die Bridge
**sofort ab**, statt die restlichen Schritte ebenfalls ins Leere laufen zu
lassen. Danach wartet sie die **doppelte `cd_time`** und beginnt von vorn.

Eine Antwort des Geräts mit einem JSON-RPC-Fehler bricht *nicht* ab - das Gerät
ist ja ansprechbar, es lehnt nur diesen einen Befehl ab.

Nach `watchdog_failure_threshold` Abbrüchen in Folge meldet der
Health-Endpoint 503, der Supervisor startet das Add-on neu, und
*Communication established* wechselt von `INIT` auf `FAIL`. Versucht wird
danach trotzdem unbegrenzt weiter, falls der Watchdog nicht aktiviert ist.

```
18:19:57  [1/10] Marstek.GetDevice
18:19:59  Initialisierung bei Marstek.GetDevice abgebrochen (Timeout) -
          das Geraet ist nicht ansprechbar. Neuer Versuch in 12s (Versuch 1/2)
18:20:13  Communication established = FAIL (2 Init-Versuche gescheitert)
18:20:41  Initialisierung abgeschlossen - Communication established = ON
```

## Kommunikationsstatus in Automationen

| Entity | Zustaende | geeignet fuer |
|---|---|---|
| `sensor.<...>_system_communication` - *Communication established* | `ON` / `INIT` / `FAIL` | Anzeige, Benachrichtigungstext |
| `binary_sensor.<...>_system_comm_ok` - *Device connectivity* | `on` / `off` (`device_class: connectivity`) | Bedingungen und Trigger in Automationen |

`INIT` bedeutet: die Bridge startet oder wartet darauf, dass das Gerät wieder
ansprechbar wird. `FAIL` heißt: der Watchdog hat ausgelöst.

```yaml
# Benachrichtigen, sobald der Speicher nicht mehr antwortet
triggers:
  - trigger: state
    entity_id: binary_sensor.marstek_..._system_comm_ok
    to: "off"
    for: "00:02:00"
```

Der Binärsensor ist dafür der robustere Trigger: Er ist genau dann `on`, wenn
der Zustand `ON` lautet, und deckt `INIT` und `FAIL` gemeinsam ab. So bekommst
du auch dann eine Meldung, wenn die Bridge dauerhaft in der Init-Schleife
hängt und nie bis `FAIL` kommt.

## Fehlersuche

| Symptom | Ursache / Lösung |
|---|---|
| Keine Antwort auf UDP | Open API in der App aktiv? Port korrekt? Gleiches Subnetz? `local_udp_port` auf den Geräteport setzen. |
| Entities „unavailable" | Add-on gestoppt oder MQTT getrennt - Log prüfen. |
| *Communication established* = FAIL | Speicher antwortet nicht; `request_timeout`/`request_retries` erhöhen. |
| Add-on startet ständig neu | Watchdog greift; `watchdog_failure_threshold` erhöhen oder Watchdog deaktivieren. |
| `set_result` false | Modus/Parameter vom Modell nicht unterstützt (Doku Kapitel 4). |
