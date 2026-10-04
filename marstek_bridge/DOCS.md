# Marstek Self-consumption Bridge - Konfiguration

Die Optionen sind nach Themen gruppiert:

| Gruppe | Inhalt |
|---|---|
| `marstek_network_settings` | Erreichbarkeit des Speichers im LAN |
| `mqtt_settings` | Broker und Auto-Discovery |
| `message_settings` | Zeitverhalten der UDP-Kommunikation |
| `additions_status_requests` | optionale Abfrage und Startwerte |
| `passiv_mode_settings` | Grenzen und Startwerte des Passive-Modus |
| `plan_settings` | Lade- und Entladeplanung |
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
| `passive_jitter` | `0` | Wechselt den gesendeten Wert um ±diesen Betrag, damit das Gerät nicht selbst abschaltet. `0` = aus. |
| `passive_keepalive_interval` | `0.0` | Abstand zwischen zwei Keepalives in Sekunden. `0` = halbe `cd_time`. |
| `passive_keepalive` | `false` | Sendet den Passive-Befehl automatisch alle `cd_time/2` Sekunden erneut, solange Passive aktiv ist. Bei aktiver Selbstregelung passiert das ohnehin immer. |
| `self_regulation_enabled` | `false` | Startzustand der Selbstregelung (auch als Switch in HA). |
| `self_regulation_gain` | `0.8` | Anteil der Abweichung je Regeltakt. |
| `self_regulation_average_window` | `5.0` | Mittelungsfenster in Sekunden vor jedem Kommando. |
| `self_regulation_export_margin` | `5.0` | Zusätzlicher Abschlag in Prozent **der Korrektur** bei Einspeisung. |
| `self_regulation_topic` | *(leer)* | Topic des Regelwerts (Netzleistung, Bezug positiv). Leer = `<mqtt_base_topic>/energy_control/regulation_input`. |
| `self_regulation_reserve` | `12` | Obere Kante des Haltebands und Ziel jeder Korrektur. |
| `self_regulation_deadband_percent` | `0.0` | Skaliert das Totband linear mit dem Sollwert (nur beim Hochregeln). `0` = aus. |
| `self_regulation_underdelivery` | `25` | Abweichung von der erwarteten Ausgangsleistung, ab der nicht korrigiert wird. `0` = aus. |
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
| `log_level` | `info` | `trace` \| `debug` \| `calc` \| `plan` \| `info` \| `warning` \| `error`. Siehe unten. |
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

**Die `cd_time` muss zum Takt passen.** Das Gerät fällt aus dem Passive-Modus,
wenn länger als `cd_time` kein Kommando kommt. Liegt der Takt dicht darunter,
reicht ein einzelner verlorener UDP-Frame - der nächste Versuch braucht ein
paar Sekunden, und die Frist ist abgelaufen:

```
WARNING  Knappes Timing: Regeltakt 10s bei cd_time 10s - nur 0s Reserve.
         Ein einzelnes verlorenes Kommando wirft das Geraet aus dem
         Passive-Modus. Empfehlung: cd_time auf mindestens 20s, oder
         request_retries auf 1
```

Die Warnung erscheint, sobald die `cd_time` kleiner ist als das Doppelte des
Takts. Geprüft wird gegen den **tatsächlich eingestellten** Wert der Entity
*Passive cd time*, nicht gegen `passive_cd_time_default` - der kann durch
`restore_state` oder eine Änderung zur Laufzeit davon abweichen. Deshalb läuft
die Prüfung beim Start, bei jeder Änderung der `cd_time` und darüber hinaus
alle zehn Minuten.

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

### Eigenabschaltung des Geräts

Das Gerät überwacht offenbar selbst, ob sich an seinem Eingang etwas tut, und
fährt die Leistung nach ein bis zwei Minuten ohne erkennbare Änderung auf 0
zurück - unabhängig von `cd_time` und Keepalive. Im Alltag fällt das nicht auf,
weil ständig Verbraucher schalten. Bei konstanter Grundlast, etwa nachts oder
wenn niemand zuhause ist, schaltet der Speicher dagegen immer wieder ab.

`passive_jitter` wechselt den gesendeten Wert deshalb abwechselnd um wenige
Watt nach oben und unten:

```
interner Sollwert 150 W, Jitter 2 W
gesendet: 148, 152, 148, 152, ...
```

Betroffen ist nur der gesendete Wert. Der interne Sollwert und damit die
gesamte Regelrechnung bleiben unberührt, und im Mittelungsfenster hebt sich der
Wechsel ohnehin auf.

Nicht gewechselt wird bei einem Sollwert von 0 W und **am Deckel**. Dort liegt
die Last über dem, was der Speicher liefern darf - der Eingang schwankt also
ohnehin kräftig, das Gerät sieht genug Bewegung. Hinzu kommt, dass die Anhebung
am Deckel abgeschnitten würde und der Wechsel nur noch nach unten wirkte:

| Sollwert | gesendet |
|---|---|
| 200 W (am Deckel) | 200, 200, 200, … |
| 150 W | 147, 153, 147, … |
| 60 W | 57, 63, 57, … |
| 0 W | 0, 0, 0, … |

### Wenn das Gerät weniger liefert als befohlen

Das Gerät reduziert seinen Ausgang zeitweise selbstständig. Für die Regelung
sieht das aus wie zusätzlicher Verbrauch: Der Netzwert steigt, also wird nach
oben korrigiert. Nimmt das Gerät seine Leistung später wieder auf, liegt der
Sollwert um genau diesen Betrag zu hoch - und es wird eingespeist.

**Unmittelbar vor jedem Regeltakt** fragt die Bridge deshalb `ES.GetStatus` ab.
Zu diesem Zeitpunkt ist das Gerät auf die aktuelle Vorgabe eingeschwungen, die
Meldung gehört also zur richtigen Vorgabe. Eine Abfrage kurz *nach* dem
Kommando würde noch den alten Zustand zeigen. Solange die Selbstregelung läuft,
entfällt dafür das zyklische `es_status`-Polling.

**Der Verlust wird gelernt.** Das Gerät stellt nicht exakt den vorgegebenen
Wert ein - zwischen Vorgabe und `ongrid_power` liegt ein weitgehend konstanter
Abstand:

| Vorgabe | gemeldet | Verlust |
|---|---|---|
| 130 W | 115 W | 15 W |
| 300 W | 285 W | 15 W |

Absolut, nicht proportional. Die Bridge führt diesen Offset als gleitenden
Mittelwert nach, beginnend beim ersten Messwert. Erwartet wird dann
`Vorgabe − Offset`.

**Erkennung und Reaktion.** Liegt die Meldung mehr als `underdelivery` Watt
unter der Erwartung, hat das Gerät eigenmächtig reduziert. Dann wird das
Mittelungsfenster verworfen - seine Werte sind verfälscht - und derselbe
Sollwert erneut gesendet, was zugleich der Versuch ist, das Gerät wieder auf
die Vorgabe zu bringen:

```
CALC     Geraet liefert 115 W bei Vorgabe 130 W (erwartet 116 W, Offset 14.4 W)
WARNING  Geraet hat den Ausgang eigenmaechtig reduziert: gemeldet 60 W,
         erwartet 108 W (48 W fehlen). Der Anstieg an der Klemme geht auf den
         Speicher zurueck - keine Korrektur, Sollwert 123 W wird erneut gesendet.
```

Eine Meldung von 0 W bedeutet, dass das Gerät innerhalb des Taktes bereits
abgeschaltet hat - sie wird als sehr große Abweichung erkannt und braucht keine
Sonderbehandlung.

**Schlägt die Abfrage fehl**, wird ebenfalls nicht korrigiert, sondern nur der
alte Wert nachgesendet. Ohne verlässliche Auskunft über den Zustand des Geräts
ist Stillhalten die sichere Wahl.

### Der Zeitplan eines Regeltakts

```
t=0      Kommando raus, Countdown des Geräts startet neu
         ├─ freies Fenster: battery, pv und andere Abfragen
t=8      Mittelungsfenster beginnt, Messwerte werden gesammelt
t=13     ES.GetStatus vor dem Takt (Reserve = request_delay + request_timeout)
t=15     Mittelwert bilden, rechnen, Kommando raus
```

Beispiel für `passive_keepalive_interval: 15` und
`self_regulation_average_window: 5`.

**Das Kommando geht pünktlich zum Takt raus.** Die Abfrage davor braucht Zeit -
Mindestpause plus Antwort - und der Takt startet um genau diese Reserve früher.
Ohne das würde sich jeder Takt um die Dauer der Abfrage nach hinten schieben
und die Marge zur `cd_time` schrumpfen.

**Andere Abfragen** laufen im freien Fenster zwischen Kommando und
Mittelungsfenster. Eine Abfrage, die das Doppelte ihres Intervalls überfällig
ist, läuft trotzdem - sie kann nicht verhungern. Bei kurzem Takt bleibt
allerdings kaum Platz: Bei 10 Sekunden Takt, 5 Sekunden Fenster und 2 Sekunden
Reserve sind es gerade drei Sekunden.

**Die `cd_time` muss zum Takt passen.** Das Gerät fällt aus dem Passive-Modus,
wenn länger als `cd_time` kein Kommando kommt. Liegt der Takt dicht darunter,
reicht ein einzelner verlorener UDP-Frame - der nächste Versuch braucht ein
paar Sekunden, und die Frist ist abgelaufen:

```
WARNING  Knappes Timing: Regeltakt 10s bei cd_time 10s - nur 0s Reserve.
         Ein einzelnes verlorenes Kommando wirft das Geraet aus dem
         Passive-Modus. Empfehlung: cd_time auf mindestens 20s, oder
         request_retries auf 1
```

Die Warnung erscheint, sobald die `cd_time` kleiner ist als das Doppelte des
Takts. Geprüft wird gegen den **tatsächlich eingestellten** Wert der Entity
*Passive cd time*, nicht gegen `passive_cd_time_default` - der kann durch
`restore_state` oder eine Änderung zur Laufzeit davon abweichen. Deshalb läuft
die Prüfung beim Start, bei jeder Änderung der `cd_time` und darüber hinaus
alle zehn Minuten.

**Die Verstärkung muss zum Takt passen.** Das Gerät braucht rund 20 Sekunden
bis zum Einschwingen. Ist der Takt kürzer, wird mehrfach auf denselben Fehler
korrigiert, und die wirksame Verstärkung ist ein Vielfaches der eingestellten:

| Takt | maximal sinnvolle Verstärkung |
|---|---|
| 5 s | 0,25 |
| 10 s | 0,5 |
| 15 s | 0,7 |
| 20 s | 0,9 |

Die Bridge warnt beim Start, wenn `self_regulation_gain` deutlich über diesem
Richtwert liegt.

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

## Lade- und Entladeplanung

Die Gruppe *Marstek Energy Plan* schreibt die Flugbahn des Speichers bis zum
PV-Beginn fort. Sie **greift nicht in die Regelung ein** - der Deckel bleibt in
deiner Hand oder in der einer HA-Automation, die sich an *Required cap*
orientieren kann.

### Was gerechnet wird

```
nutzbar       = (SOC − target_soc) × bat_cap / 100
Required cap  = nutzbar / Stunden bis PV-Beginn
Projected SOC = SOC − Last × Stunden / bat_cap × 100
Missing room  = Prognose − freier Platz bei PV-Beginn
```

Die Last ist dabei der Verbrauch auf der Phase des Speichers: Netzwert von der
Messklemme plus die Ausgangsleistung aus `ES.GetStatus`.

Gerechnet wird mit dem **Mittel über `plan_load_window`** (Standard 15 Minuten),
nicht mit dem Momentanwert. Die Fortschreibung läuft über viele Stunden - ein
gerade anlaufender Kühlschrank würde sonst die halbe Nacht hochgerechnet und
die Flugbahn sprunghaft verändern. *Current load* zeigt weiterhin den
Momentanwert, *Load average* den geglätteten.

Die **Grundlast** lernt die Bridge aus den Stunden zwischen 1 und 5 Uhr und
glättet sie über mehrere Nächte; sie dient als Rückfallwert, wenn gerade keine
Messung vorliegt.

### Gelernte Werte überleben Neustarts

Grundlast, Prognose-Faktor und der Verlust-Offset des Geräts werden in
`/data/marstek_state.json` unter `plan` gesichert und beim Start übernommen -
höchstens alle fünf Minuten geschrieben, damit die Datei nicht ständig in
Bewegung ist. Die Grundlast bräuchte sonst nach jedem Neustart eine ganze
Nacht, der Prognose-Faktor mehrere Tage.

### Prognose-Faktor

Prognosen treffen selten genau, und nicht alles, was erzeugt wird, kommt im
Speicher an - der gleichzeitige Verbrauch geht vorher ab. Beide Effekte
zusammen fängt ein gelernter Faktor ein.

Beim Datumswechsel wird die Prognose zur Prognose des laufenden Tages und der
Stand des eigenen PV-Zählers festgehalten. Am nächsten Wechsel steht fest, was
wirklich produziert wurde:

```
PLAN  Tagesabschluss 2026-10-02: Prognose 4406 Wh, produziert 3100 Wh
      -> Faktor 70 % (geglaettet 70 %)
```

*Forecast tomorrow* zeigt weiterhin die Rohprognose, *Forecast corrected* den
mit dem Faktor multiplizierten Wert. Gerechnet wird mit dem korrigierten - im
Beispiel sinkt *Missing room* damit von 1074 Wh auf 0, weil die 4406 Wh der
Rohprognose bei diesem Gerät realistisch 3100 Wh bedeuten.

### Während der PV-Produktion

Zwischen `plan_pv_start` und `plan_pv_end` meldet der Planer den Zustand `pv`
und **lässt die Flugbahn aus**. Sie wäre dort ohne Aussage: Sie schreibt den
Verbrauch bis zum nächsten PV-Beginn fort und kennt die Energie nicht, die
gerade einlädt - um 12:36 ergäbe das eine Vorhersage über 23 Stunden mit einem
projizierten SOC von −27 %, während der Speicher tatsächlich gerade mit 585 W
geladen wird.

*Projected SOC* und *Limit reached at* bleiben in dieser Zeit leer. *Missing
room* dagegen wird weiter gerechnet, nur anders herum: gegen den **aktuellen**
SOC und gegen den Teil der Prognose, der noch aussteht. Damit steht dort eine
Live-Antwort auf die Frage, ob heute noch Energie verschenkt wird.

```
PLAN  PV-Zeitfenster (12:00 bis 18:00) - keine Flugbahn.
      Heute bisher 900 Wh erzeugt, erwartet 2100 Wh
```

Das Fenster gehört saisonal nachgezogen - im Sommer kommt bis etwa 20 Uhr noch
Ladung, im Herbst ist um 18 Uhr Schluss.

**Die Uhrzeit allein genügt nicht.** Der Zustand `pv` verlangt zusätzlich, dass
tatsächlich etwas ankommt - mindestens `plan_pv_min_power`. An einem trüben Tag
bleibt die Flugbahn also erhalten, obwohl das Fenster offen ist, und das ist
richtig: Dort sagt sie etwas aus. Nach dem letzten Messwert über der Schwelle
läuft die Erkennung noch zehn Minuten nach, damit eine vorbeiziehende Wolke den
Zustand nicht hin und her kippt.

| Uhrzeit | letzte PV-Meldung über 50 W | Zustand `pv` |
|---|---|---|
| 13:30 | nie | nein |
| 13:30 | gerade eben | ja |
| 13:30 | vor 5 min | ja |
| 13:30 | vor 15 min | nein |
| 19:30 | gerade eben | nein |
| 10:30 | gerade eben | nein |

### Warum eine Grenze und kein Boden

Erreicht der Speicher den DOD-Stopp, liefert er nichts mehr - verbraucht sich
im Standby aber weiter und lädt sich irgendwann mit über einem Kilowatt aus dem
Netz nach. Das ist doppelt teuer: Du kaufst Energie und schickst sie mit
Wandlungsverlusten durch den Akku. `plan_target_soc` sollte deshalb mit Abstand
darüber liegen, Vorschlag 20 % bei einem DOD-Stopp um 12 %.

### Warum der Planer nicht pauschal drosselt

Ein Budget, das die Energie gleichmäßig über die Nacht verteilt, wäre schädlich.
Bei 4160 Wh und 90 % SOC ergäbe das einen Deckel von 166 W - ein Abend mit
350 W Verbrauch würde dann 900 bis 1200 Wh aus dem Netz kaufen, obwohl die
Grenze gar nicht in Gefahr ist. Von 90 % aus landet man selbst mit kräftigem
Abend bei 22 %.

Der Planer ist deshalb als **Wächter** gedacht: Er rechnet die Flugbahn fort und
meldet `limit` nur, wenn sie tatsächlich unter die Grenze führt. Der
Gefahrenfall ist nicht der kräftige Abend, sondern der niedrige Start nach
trüben Tagen.

### Was die Prognose bringt

Nicht das Strecken der Entladung spart Energie - jede Wattstunde aus dem
Speicher ist eine nicht gekaufte, egal wann. Verloren geht Energie nur, wenn
mittags PV anfällt, während der Speicher schon voll ist. Dafür braucht es
**Platz**, und den schafft nur Verbrauch:

| Prognose | nötiger SOC bei PV-Beginn |
|---|---|
| 1 kWh | 76 % |
| 2 kWh | 52 % |
| 3 kWh | 28 % |

Dem gegenüber steht, was das Haus über Nacht überhaupt abnehmen kann: bei 80 W
mittlerer Last in 18 Stunden rund 35 Prozentpunkte. *Missing room* und
*Expected spill* zeigen die Lücke täglich an - und damit, was eine in die Nacht
verschobene Waschmaschine wert wäre.

### Erkennung einer Ladung aus dem Netz

Wird `ongrid_power` stärker negativ als `plan_charge_threshold`, lädt der
Speicher aus dem Netz. Unterschieden wird:

| Zustand | Bedeutung |
|---|---|
| `off` | keine Ladung |
| `intended` | wir haben negative Leistung befohlen |
| `unexpected` | das Gerät lädt von sich aus |

```
WARNING  Selbstnachladung erkannt bei SOC 9 % - Geraet laedt mit 1480 W,
         befohlen waren 150 W
```

SOC, Leistung und Zeitpunkt des letzten unerwarteten Vorfalls bleiben als
eigene Entities stehen. Damit lässt sich über einige Tage ausmessen, bei
welchem SOC das Gerät tatsächlich nachzuladen beginnt - und `plan_target_soc`
anschließend gezielt setzen statt zu schätzen.

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

## Was bei Timeouts passiert

Der Speicher ist zeitweise so beschäftigt, dass er einzelne Anfragen gar nicht
beantwortet. Das ist **kein Kommunikationsausfall** und wird deshalb auch nicht
als solcher gemeldet:

| Vorgang | Wirkung |
|---|---|
| einzelner Timeout | *Request failures* zählt hoch, *Last request failure* bekommt einen Zeitstempel. `Communication established` bleibt auf `ON`. |
| `watchdog_failure_threshold` Fehler in Folge | erst jetzt `FAIL`, Health-Endpoint unhealthy, Neu-Initialisierung |
| Regelsignal reagiert nicht | eigene Entity *Regulation signal* wechselt auf `stuck`, Sollwert auf 0 W. `Communication established` bleibt unberührt. |

Bisher sprang `Communication established` schon beim ersten Timeout auf `FAIL`
und beim nächsten Erfolg zurück - bei einem Gerät, das regelmäßig kurz nicht
antwortet, flatterte die Entity dadurch ständig und war für Automationen
unbrauchbar. Jetzt bedeutet `FAIL`, was es sagt: Das Gerät ist über mehrere
Versuche hinweg nicht erreichbar.

Für eine Automation auf „Gerät zickt" eignet sich *Request failures*: Steigt
der Zähler über Stunden kaum, läuft alles rund; springt er in Schüben, ist der
Speicher überlastet - dann helfen ein höheres `request_timeout` oder ein
längerer Regeltakt.

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
