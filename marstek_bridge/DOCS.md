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
| `passive_keepalive_interval` | `0.0` | Abstand zwischen zwei Keepalives in Sekunden. `0` = halbe `cd_time`. |
| `passive_keepalive` | `false` | Sendet den Passive-Befehl automatisch alle `cd_time/2` Sekunden erneut, solange Passive aktiv ist. Bei aktiver Selbstregelung passiert das ohnehin immer. |
| `self_regulation_enabled` | `false` | Startzustand der Selbstregelung (auch als Switch in HA). |
| `self_regulation_gain` | `0.8` | Anteil der Abweichung je Regeltakt. |
| `self_regulation_average_window` | `5.0` | Mittelungsfenster in Sekunden vor jedem Kommando. |
| `self_regulation_export_margin` | `5.0` | Zusätzlicher Abschlag in Prozent bei einer Einspeise-Korrektur. |
| `self_regulation_topic` | *(leer)* | Topic des Regelwerts (Netzleistung, Bezug positiv). Leer = `<mqtt_base_topic>/energy_control/regulation_input`. |
| `self_regulation_reserve` | `12` | Obere Kante des Haltebands und Ziel jeder Korrektur. |
| `self_regulation_deadband_percent` | `0.0` | Skaliert das Totband linear mit dem Sollwert (nur beim Hochregeln). `0` = aus. |
| `self_regulation_stuck_limit` | `3` | Kommandos ohne Reaktion, bis das Regelsignal als unbrauchbar gilt. `0` = aus. |
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

Der Passive-Modus läuft nach `cd_time` aus, es muss also ohnehin regelmäßig ein
Kommando raus. **Dieser Keepalive-Takt ist der Regeltakt** - ein eigener
Zeitplan wäre nur eine zweite Uhr für dieselbe Sache.

```
je Takt (passive_keepalive_interval):
    Mittel der letzten average_window Sekunden bilden
    liegt es außerhalb von Halteband und Totband? → korrigieren
    Kommando senden (korrigiert oder unverändert)

dazwischen, höchstens einmal je Takt:
    Mittel unter band_low? → Einspeise-Korrektur mit voller Verstärkung
    und export_margin Prozent zusätzlichem Abschlag, nie unter base_load
```

Gemittelt wird nur über Werte, die **nach dem letzten Kommando** eingetroffen
sind. Solange das Fenster nicht voll ist, wird nicht gerechnet - während das
Gerät noch auf die alte Vorgabe hinläuft, ist ein Messwert nichts wert.

**Die Verstärkung muss zum Takt passen.** Das Gerät braucht rund 10 Sekunden
Totzeit und weitere 10 bis 15 Sekunden Rampe. Bei einem Takt von 20 Sekunden
misst die Bridge in den Sekunden 15 bis 20, also bei etwa 85 Prozent der
Rampe - der Messwert ist systematisch zu hoch, die Korrektur fiele zu groß
aus. Solange `gain` **unter** diesem Anteil bleibt, konvergiert es trotzdem.
0,7 bis 0,8 sind passend; bei 0,9 wird es grenzwertig. Alternativ den Takt auf
25 Sekunden ziehen, dann ist die Rampe durch.

Simulation mit 10 s Totzeit, 5 s Rampe, Messung jede Sekunde, ±3 W Rauschen:

| | Korrekturen | eingespeist | bezogen |
|---|---|---|---|
| Lastanstieg 60 → 400 W, gain 0,8, Takt 20 s | 5 | 175 Ws | 13 634 Ws |
| Lastanstieg 60 → 400 W, gain 0,7, Takt 20 s | 6 | 31 Ws | 14 614 Ws |
| Lastanstieg 60 → 400 W, gain 0,8, Takt 25 s | 3 | 0 Ws | 14 575 Ws |
| Lastabfall 500 → 80 W, gain 0,8, Takt 20 s | 5 | 11 194 Ws | 2 547 Ws |

**Einspeisung zwischen zwei Takten** löst eine Sofortkorrektur aus, aber erst
wenn ein volles Mittelungsfenster seit dem letzten Kommando vorliegt - ein
einzelner negativer Wert während des Einschwingens ist kein Grund zu handeln.
Und höchstens einmal je Takt: Das Fenster ist nach wenigen Sekunden wieder
voll, das Gerät hat zu dem Zeitpunkt aber noch nicht einmal angefangen zu
reagieren. Ohne diese Sperre würde die Bridge im Sekundentakt nachsetzen und
den Sollwert weit unter den nötigen Wert treiben.

### Statusabfragen

`ES.GetStatus` und die übrigen Abfragen laufen im ruhigen Fenster zwischen zwei
Regeltakten: nicht in den ersten `poll_quiet_after_write` Sekunden nach einem
Kommando, und nicht in den letzten Sekunden davor, in denen die Messwerte für
den Mittelwert gesammelt werden. Eine Abfrage, die das Doppelte ihres
Intervalls überfällig ist, läuft trotzdem.

### Was das Gerät meldet

Jede `ES.GetStatus`-Antwort erscheint auf `calc` mit den Werten, die für die
Fehlersuche zählen:

```
CALC  Geraet meldet: Netz 33 W | Batterie -40 W | PV 0 W | SOC 62 % | Insel 0 W
```

Damit lässt sich im Nachhinein entscheiden, ob ein Sprung im Messwert vom
Speicher kam oder von einem Verbraucher: Liefert `Netz` weiter plausible Werte
und `Batterie` die befohlene Leistung, hat der Speicher gearbeitet.

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

### Abfragen nur im Ruhezustand

Während die Selbstregelung auf die Reaktion des Geräts oder auf das Einpendeln
wartet, rechnet der Speicher an der neuen Vorgabe und antwortet auf
Statusabfragen oft gar nicht mehr - die Praxis zeigt Timeouts von mehreren
Sekunden. Die gelieferten Werte wären in dieser Phase ohnehin Momentaufnahmen
eines Übergangs.

`poll_only_at_rest` verschiebt Abfragen deshalb, bis die Regelung eingependelt
ist und nichts zu korrigieren hat. Eine Abfrage, die das Doppelte ihres
Intervalls überfällig ist, läuft trotzdem - sie kann nicht verhungern, auch
wenn die Regelung dauernd beschäftigt ist.

Das ist die weiter gefasste Fassung von `poll_quiet_after_write`: Die drei
Sekunden dort decken nur den Moment nach einem Schreibkommando ab, während der
Speicher in Wahrheit 20 bis 25 Sekunden mit dem Einschwingen beschäftigt ist.
Ist die Selbstregelung aus, greift weiterhin nur die Ruhezeit.

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

## Wenn das Regelsignal ausfällt

Zwei Ausfallarten werden erkannt:

**Es kommt nichts mehr.** Bleiben Werte länger als `input_timeout` aus - HA
neu gestartet, Automation deaktiviert, Broker weg - fällt der Sollwert auf 0 W.

**Es kommt immer derselbe Wert.** Ein hängender Sensor, der weiter publiziert,
ist heimtückischer: `input_timeout` greift nicht, und für die
Einpendel-Erkennung sieht ein eingefrorener Wert wie ein perfekt ruhiges Signal
aus. Die Bridge würde korrigieren, keine Reaktion sehen, nach
`reaction_timeout` weitermachen, den Wert wieder für ruhig halten und erneut
korrigieren - der Sollwert klettert alle 20 Sekunden ein Stück, bis er am
Deckel steht und der Speicher unbemerkt ins Netz einspeist.

Erkannt wird das an der Reaktionsphase: Wir befehlen eine deutliche Änderung
und sehen keinerlei Bewegung. Einmal kann harmlos sein, `stuck_limit` Mal in
Folge ist physikalisch unmöglich. Dann:

```
WARNING  Keine erkennbare Reaktion nach 15s (Bewegung 0.0 W, noetig 8.1 W,
         befohlen 27 W) - Ausfall 3/3
ERROR    Regelsignal reagiert nicht - 3 Kommandos ohne Bewegung, Messwert
         steht bei 42.0 W. Sollwert wird auf 0 W gesetzt, die Regelung ruht
         bis sich der Messwert wieder bewegt.
ERROR    Communication established = FAIL
```

*Communication established* bleibt auf `FAIL`, auch wenn die Kommunikation mit
dem Speicher selbst einwandfrei läuft - eine Automation auf
`binary_sensor.<...>_system_comm_ok` schlägt damit an. Bewegt sich der Messwert
wieder um mehr als `settle_tolerance`, nimmt die Regelung den Betrieb auf und
der Zustand geht zurück auf `ON`.

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
