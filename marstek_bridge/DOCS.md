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
| `self_regulation_settle_samples` | `3` | So viele Messwerte in Folge müssen dicht beieinander liegen. |
| `self_regulation_settle_tolerance` | `10` | Erlaubte Spanne dieser Messwerte in Watt. |
| `self_regulation_settle_max_wait` | `60` | Pendelt es sich nicht ein, wird nach dieser Zeit trotzdem korrigiert. `0` = unbegrenzt warten. |
| `self_regulation_settle_gain` | `0.8` | Anteil der Abweichung beim Hochregeln. |
| `self_regulation_settle_gain_down` | `1.0` | Anteil beim Runterregeln - 1,0 ist der exakte Wert. |
| `self_regulation_fast_threshold` | `100` | Abweichung, ab der aus dem Ruhezustand ohne Wartezeit korrigiert wird. `0` = aus. |
| `self_regulation_reaction_timeout` | `15.0` | Wartezeit auf die Reaktion des Geräts, bevor das Einpendeln beginnt. `0` = nicht warten. |
| `self_regulation_timeout_gain` | `0.5` | Anteil nach Ablauf von `settle_max_wait`. |
| `self_regulation_topic` | *(leer)* | Topic des Regelwerts (Netzleistung, Bezug positiv). Leer = `<mqtt_base_topic>/energy_control/regulation_input`. |
| `self_regulation_reserve` | `12` | Obere Kante des Haltebands und Ziel jeder Korrektur. |
| `self_regulation_band_low` | `0` | Untere Kante des Haltebands. Darunter wird zurückgeregelt. |
| `self_regulation_base_load` | `0` | Grundlast der Phase als **Untergrenze** für den Sollwert. `0` = aus. |
| `self_regulation_deadband` | `10` | Abweichung des **Netzwerts** ab der Reserve, unter der nicht geregelt wird (nur beim Hochregeln). |
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
Netzwert > Reserve      → Abweichung = Netzwert − Reserve
band_low ≤ N ≤ Reserve  → Abweichung = 0        Halteband, nichts tun
Netzwert < band_low     → Abweichung = Netzwert − Reserve

Schritt  = Abweichung × gain        gain = settle_gain | timeout_gain | 1,0
Sollwert = clamp(Sollwert + Schritt, 0, "Passive power")
```

### So regelt die Bridge

Der Speicher braucht nach einem Kommando rund **10 Sekunden Totzeit** und
weitere 10 bis 15 Sekunden Rampe, bis die neue Leistung anliegt. Ein Regler,
der alle 5 Sekunden nachfasst, korrigiert denselben Fehler vier- bis fünfmal,
bevor die erste Korrektur überhaupt messbar ist - und schwingt.

Genauso wenig aussagekräftig ist der erste Messwert nach einem **Lastwechsel** -
er liegt meist mitten in der Änderung. Eine Korrektur darauf trifft einen
Zwischenstand und muss sofort nachgebessert werden; auch daraus entsteht
Schwingen.

Die Bridge korrigiert deshalb grundsätzlich nur auf ein **ruhiges, bestätigtes
Signal**, in zwei Phasen:

1. **Reaktion abwarten.** Während der Totzeit steht der Messwert still. Ein
   kurzes Stichprobenfenster würde das fälschlich als „eingependelt" werten und
   auf einen Zustand korrigieren, den das Gerät noch gar nicht erreicht hat.
   Die Bridge merkt sich deshalb den Messwert vor dem Kommando und die
   befohlene Änderung und wartet, bis sich der Messwert um mindestens 30 % der
   erwarteten Bewegung geändert hat. Bleibt sie aus - etwa weil die Korrektur
   kleiner war als das Rauschen - geht es nach `reaction_timeout` trotzdem
   weiter.
2. **Ruhe abwarten.** Erst jetzt zählt das Fenster der letzten
   `settle_samples` Messwerte. Liegen sie innerhalb von `settle_tolerance`,
   steht das System und es wird korrigiert - auf den **Mittelwert** des
   Fensters, nicht auf den zufällig letzten Einzelwert.
3. Nach jedem Kommando beginnt beides von vorn.
4. Beruhigt sich das Signal innerhalb von `settle_max_wait` nicht, wird
   trotzdem korrigiert, dann mit dem kleineren `timeout_gain`.

Weil die Reaktionsphase die Totzeit abdeckt, darf `settle_samples` kurz sein -
6 bis 8 Werte reichen. Das verkürzt nicht nur die Regelung, es senkt auch das
Risiko, dass mitten im Fenster ein Gerät einschaltet und die Messung verfälscht.

**Schnellpfad bei Lastwechseln.** Eine Abweichung von mehr als
`fast_threshold` ist zwangsläufig ein echtes Lastereignis - so groß wird
Rauschen nicht. Aus dem **Ruhezustand** heraus wird darauf sofort korrigiert,
ohne erst ein Fenster zu füllen. Ruhezustand heißt: Das Fenster war
eingependelt und es gab nichts zu korrigieren.

Während das Gerät auf eine eigene Korrektur hochfährt, gilt der Schnellpfad
ausdrücklich **nicht**. Dort durchläuft der Messwert dieselbe Strecke und wäre
genauso weit vom Ziel entfernt - eine Korrektur mitten im Einschwingen würde
genau das Schwingen zurückholen, das die Einpendel-Erkennung beseitigt.

Simulation, Kühlschrank mit 130 W schaltet ein und nach zwei Minuten wieder
aus, Grundlast 50 W:

| | Kommandos | eingespeist | bezogen |
|---|---|---|---|
| ohne Schnellpfad | 8 | 2 424 Ws | 6 218 Ws |
| mit Schnellpfad (100 W) | 7 | 1 758 Ws | 5 415 Ws |

**Verstärkung je Richtung.** Nach unten ist 1,0 der exakte Wert: Der neue
Sollwert ist `Sollwert + Netzwert − Reserve`, damit landet der Netzwert genau
auf der Reserve. Ein Fehler fällt dabei auf die Bezugsseite und ist harmlos.
Nach oben bleibt mit `settle_gain` eine Marge, weil ein Überschießen dort
Einspeisung bedeutet.

**Untergrenze Grundlast.** `base_load` ist die Leistung, die auf dieser Phase
ohnehin verbraucht wird. Ein Abwärtsschritt stoppt dort, statt bis auf 0 W
durchzufallen - der anschließende Wiederaufstieg wird dadurch kürzer. Das
Ventil dazu: Die Grenze bremst nur den Schritt *von oben*. Wird danach immer
noch Einspeisung gemessen, steht der Sollwert bereits auf der Grundlast und der
nächste Schritt darf darunter. Eine zu hoch eingestellte Grundlast kann so
keine dauerhafte Einspeisung erzwingen, sie kostet nur einen Zyklus.

**Den Wert richtig ansetzen:** Sende testweise verschiedene Sollwerte im
Passive-Modus, wenn sonst nichts läuft, und nimm den, bei dem die Messklemme
etwa die **Reserve** anzeigt - nicht 0 W. Zeigt sie 0, liegt der Arbeitspunkt
genau an der unteren Bandkante, das Rauschen kippt ihn ständig ins Negative,
und die Untergrenze bindet bei jeder Rückkehr zur Grundlast. Bei 50 W
Grundverbrauch und 8 W Reserve ist also ein Wert um 42 richtig, nicht 50.

Ob die Unruhe von der eigenen Korrektur oder von einem Lastwechsel stammt,
spielt dabei keine Rolle - behandelt wird beides gleich.

Simulation mit 6 Stichproben, Toleranz 8 W, Grundlast 40 W, ±3 W Rauschen:

| Szenario | Kommandos | eingespeist | bezogen |
|---|---|---|---|
| Lastabfall 500 → 80 W | 1 | 9 161 Ws | 1 347 Ws |
| Lastanstieg 60 → 400 W | 3 | 0 Ws | 11 542 Ws |
| Lastabfall 500 → 20 W (unter der Grundlast) | 3 | 11 212 Ws | 2 205 Ws |

Der Lastabfall wird in einem einzigen Kommando ausgeregelt. Im dritten Fall
greift das Ventil: Der erste Schritt stoppt bei 40 W, der zweite geht auf 8 W.

**Taktung der Quelle:** Je feiner der Eingang, desto genauer die Erkennung.
Bewährt hat sich ein Messwert pro Sekunde mit `settle_samples` zwischen 10 und
15 - dann gilt das System nach 10 bis 15 Sekunden Ruhe als eingeschwungen. Mit
einem 5-Sekunden-Mittel und 3 Stichproben wird die Erkennung träge und ungenau,
weil der Mittelwert die Ruhe selbst verschleift.

**`settle_tolerance` muss größer sein als das Rauschen des Sensors.** Sonst gilt
das Signal nie als eingependelt und jede Korrektur läuft über den Timeout-Pfad
mit der kleineren Verstärkung - erkennbar im Log an „seit Xs nicht
eingependelt". Bei 12 Stichproben ergibt ein Rauschen von ±3 W eine typische
Spanne von 5 W, ±5 W ergeben rund 9 W. In der Simulation kostete eine zu enge
Toleranz von 3 W gegenüber 8 W mehr als das Doppelte an eingespeister Energie,
weil jede Korrektur 40 Sekunden zu spät kam.

Jede Sollwertänderung leert das Fenster - auch der Wechsel nach *Passive* über
den Apply-Button, denn danach schwingt das Gerät ebenso ein. Der Keepalive tut
das nicht, er sendet nur denselben Wert erneut.

**Das gilt für beide Richtungen.** Auch eine Einspeisung wird erst nach dem
Einpendeln korrigiert. Während des Einschwingens rutscht der Netzwert praktisch
immer kurz ins Negative - sofort dagegenzuregeln hieße, auf ein bereits
vorbeigezogenes Ereignis zu reagieren, und erzeugt genau das Schwingen, das
vermieden werden soll. Ist der Wert nach dem Einpendeln immer noch negativ,
wird er wie jede andere Abweichung korrigiert.

Simulation mit Totzeit 10 s, Rampe 5 s, Messung alle 5 s, Lastsprung auf 250 W
und später auf 500 W:

| | Einpendeln abwarten | feste Schritte im Takt (bis 0.0.27) |
|---|---|---|
| Kommandos | 6 | 35 |
| Netz am Ende | 10 W | −46 W (schwingt) |
| ins Netz eingespeist | 0 Ws | 2034 Ws |

Die Konvergenz dauert physikalisch bedingt 40 bis 60 Sekunden, bei einem großen
Lastabfall auch zwei Minuten. Schneller geht es mit diesem Gerät nicht,
unabhängig vom Verfahren. Bricht die Last ein, während der Speicher noch hohe
Leistung abgibt, fließt die Differenz bis zur nächsten Korrektur ins Netz - das
verursacht die Last, nicht die Regelung. Wer das begrenzen will, senkt den
Deckel *Passive power*.

### Weitere Eigenschaften

* **Halteband** zwischen `band_low` (Standard 0 W) und `reserve`. Liegt der
  Netzbezug darin, passiert nichts. Ein Bezug von 4 W ist besser als die
  Reserve von 10 W - dafür Speicherleistung zurückzunehmen wäre verschenkt.
  Korrigiert wird erst, wenn der Wert das Band verlässt, und dann immer zurück
  auf die Reserve: bei −20 W also um 30 W. Bis exakt 0 W zurückzuregeln würde
  den Arbeitspunkt an die Kante legen, wo ihn das nächste Messrauschen wieder
  ins Negative kippt.

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
  Netzbezug nachgeregelt. Nach unten greift es praktisch nie, weil schon die
  Reserve allein größer ist als ein üblicher Totbandwert.
* **Ändert sich der Sollwert nicht**, wird nichts gesendet - etwa wenn er
  bereits am Deckel steht.
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

Damit ist jeder Schritt nachrechenbar: gemessener Wert, Lage zum Halteband,
Größe und Begründung des Schritts, alter und neuer Sollwert.

Wiederkehrende Meldungen ohne Konsequenz - „im Totband", „warte auf
Einpendeln" - erscheinen höchstens alle 10 Sekunden, ebenso die INFO-Zeile für
einen Messwert, der am Sollwert nichts ändert. Sonst liefe bei einem
Sekundentakt jede Sekunde eine Zeile durch.

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

**Die Konfiguration gewinnt.** Unter `control_defaults` merkt sich die Bridge,
welche Werte die Optionen `passive_power_default`, `passive_cd_time_default`
und `self_regulation_enabled` beim Speichern hatten. Wurde eine davon seitdem
geändert, wird der Konfigurationswert genommen statt des gespeicherten
Laufzeitwerts - sonst bliebe eine Änderung in der Add-on-Oberfläche wirkungslos.
Alle übrigen Optionen behalten ihren zur Laufzeit eingestellten Wert.

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
