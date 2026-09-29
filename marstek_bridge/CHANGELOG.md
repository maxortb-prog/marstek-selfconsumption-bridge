# Changelog

## 0.0.30 - 2026-09-29

- **Fix:** Lagen alle Messwerte im Totband, wurde die Wartephase nie beendet -
  die Pruefung auf das Einpendeln kam erst nach der Totbandpruefung und wurde
  deshalb uebersprungen. Ein spaeterer Lastwechsel lief dadurch in den
  Timeout-Pfad und wurde nur mit `timeout_gain` korrigiert, obwohl das Signal
  laengst ruhig war. Das Einpendeln wird jetzt zuerst ausgewertet.
- **Fix:** Der Wechsel nach *Passive* ueber den Apply-Button startet jetzt
  ebenfalls eine Wartephase. Bisher korrigierte die Bridge direkt nach dem
  Umschalten auf einen Messwert, der noch vom Umschaltvorgang stammte - beim
  Start besonders auffaellig, weil das Geraet aus dem Auto-Modus kommt und
  dort selbst regelt.
- Der Keepalive startet weiterhin keine Wartephase, da er denselben Wert
  erneut sendet.

## 0.0.29 - 2026-09-29

- Die Regelung ist jetzt in beide Richtungen gleich: auch eine Einspeisung wird
  erst nach dem Einpendeln korrigiert. Der Sofort-Pfad entfiel, weil der
  Netzwert waehrend jedes Einschwingvorgangs kurz ins Negative rutscht - sofort
  dagegenzuregeln hiess, auf ein vorbeigezogenes Ereignis zu reagieren, und hat
  erneut Schwingen erzeugt.
- `self_regulation_min_interval_down` entfaellt, es gab nur den Sofort-Pfad.
- **Fix:** Eine Senkung des Deckels und der Eingangs-Timeout senden ebenfalls
  Kommandos, haben die Einpendel-Erkennung aber nicht zurueckgesetzt. Die
  naechste Messung waere faelschlich als eingependelt gewertet worden.

## 0.0.28 - 2026-09-29

**Achtung: entfallene Optionen.** Nach dem Update einmal die Add-on
Konfiguration oeffnen und speichern.

- Die Schritt-Strategie wurde vollstaendig entfernt; es bleibt das Warten auf
  das Einpendeln. Damit entfallen `self_regulation_strategy`,
  `self_regulation_step_gain`, `self_regulation_step_up`,
  `self_regulation_step_down`, `self_regulation_min_interval`,
  `self_regulation_settle_time` und `self_regulation_fast_down`.
- Einspeisung wird jetzt immer sofort und vollstaendig korrigiert; die Sperre
  laesst sich nicht mehr abschalten. `self_regulation_min_interval_down`
  verhindert weiterhin, dass mehrere Korrekturen direkt aufeinander folgen.
- Die geschaetzte Totzeit-Kompensation ist mit der Schritt-Strategie entfallen;
  die Totzeit wird abgewartet statt geschaetzt.

## 0.0.27 - 2026-09-29

- **Neue Regelstrategie `settle` als Standard.** Statt die Totzeit des Geraets
  zu schaetzen, wartet die Bridge nach jeder Korrektur, bis sich die Messung
  wieder beruhigt hat (`settle_samples` Werte innerhalb `settle_tolerance`),
  und korrigiert dann in einem grossen Schritt (`settle_gain`, Standard 80 %).
  Hintergrund: Messungen am Geraet ergaben rund 10 Sekunden Totzeit und
  weitere 10 bis 15 Sekunden Rampe - jeder Regler mit festem Takt korrigiert in
  dieser Zeit mehrfach denselben Fehler und schwingt.
- Beruhigt sich das Signal nicht innerhalb von `settle_max_wait`, wird mit dem
  kleineren `timeout_gain` korrigiert.
- Einspeisung bricht das Warten ab und wird sofort und vollstaendig korrigiert.
- Das bisherige Verfahren bleibt als `self_regulation_strategy: step`
  erhalten. Nur dort wirken `step_gain`, `step_up`, `min_interval` und
  `settle_time`.

## 0.0.26 - 2026-09-28

- **Fix:** Eine Aenderung an `passive_cd_time_default`, `passive_power_default`
  oder `self_regulation_enabled` blieb wirkungslos, weil `restore_state` den
  alten Laufzeitwert aus `/data/marstek_state.json` darueber geschrieben hat.
  In der HA-Oberflaeche stand dann weiter der alte Wert. Die Bridge merkt sich
  jetzt, welche Konfigurationswerte beim Speichern galten, und nimmt bei einer
  Aenderung den neuen Wert aus der Konfiguration.
- Beim ersten Start nach dem Update gewinnt die Konfiguration einmalig fuer
  diese drei Werte, da aeltere State-Files die Vergleichsdaten noch nicht
  enthalten.

## 0.0.25 - 2026-09-28

- **Das Totband wirkt jetzt auf die Abweichung des Netzwerts statt auf den
  berechneten Sollwert.** Die Schwelle ist damit `reserve + deadband` und
  unabhaengig von `step_gain`: bei Reserve 8 W und Totband 5 W wird ab 13 W
  Netzbezug nachgeregelt. Bisher entsprach ein Totband von 5 W bei `gain 0.5`
  einer Abweichung von 10 W - der Regler blieb stehen, obwohl dauerhaft zu viel
  bezogen wurde.
- Statt der Sonderregel "am Anschlag gilt kein Totband" wird geprueft, ob sich
  der Sollwert ueberhaupt aendert. Aendert er sich nicht, wird nicht gesendet.

## 0.0.24 - 2026-09-28

- *Apply mode* sendet nichts mehr, wenn der Passive-Modus bereits laeuft und
  die Selbstregelung aktiv ist. Eine Automation, die zyklisch auf Apply
  drueckt, hat bisher den zuletzt berechneten - und damit oft schon veralteten
  - Sollwert dazwischengeschoben und mit dem naechsten Regelkommando
  kollidiert. Fuer einen echten Moduswechsel bleibt der Button unveraendert.
- Der Zielmodus wird nur noch protokolliert, wenn er sich tatsaechlich aendert.

## 0.0.23 - 2026-09-28

- Neue Option `poll_quiet_after_write` (Standard 3 s): nach einem
  Schreibkommando (`ES.SetMode`, `DOD.SET`, `Ble.Adv`, `Led.Ctrl`) wird keine
  Statusabfrage gestartet. Der Speicher ist direkt danach beschaeftigt und
  liess Abfragen sporadisch in den Timeout laufen. Eine ueberfaellige Abfrage
  laeuft trotzdem, sobald sie das Doppelte ihres Intervalls ueberschreitet.
- **Fix:** Schlug das Senden eines Regelkommandos fehl, hat die Bridge den
  neuen Sollwert trotzdem intern uebernommen. Der Speicher lief weiter mit dem
  alten Wert, waehrend der naechste Regelschritt von einem Wert ausging, den
  das Geraet nie bekommen hat. Der Sollwert wird jetzt zurueckgesetzt und der
  Regelwert erneut vorgemerkt.

## 0.0.22 - 2026-09-28

- Der Button *Apply mode* liest den Modus nur noch nach, wenn
  `poll_interval_mode` groesser 0 ist. Eine Automation, die zyklisch auf Apply
  drueckt, hat bisher bei jedem Druck ein `ES.GetMode` ausgeloest - auch dann,
  wenn die Abfrage per Intervall abgeschaltet war.

## 0.0.21 - 2026-09-28

**Achtung: `poll_interval` entfaellt.** Nach dem Update einmal die Add-on
Konfiguration oeffnen und speichern.

- Jede Abfrage hat ein eigenes Intervall: `poll_interval_es_status` (10 s),
  `poll_interval_battery` (300 s), `poll_interval_pv`, `poll_interval_mode`
  und `poll_interval_em` (je 0 = aus). Bisher lief ein gemeinsamer Zyklus ueber
  alle Abfragen, auch ueber die wenig ergiebigen.
- Pro Schleifendurchlauf wird hoechstens eine faellige Abfrage ausgefuehrt.
- `request_delay` ist jetzt eine Mindestpause zwischen **allen** UDP-Anfragen,
  nicht nur zwischen Polling-Schritten. Damit kollidieren Abfragen nicht mehr
  mit Regelkommandos oder dem Keepalive, was bisher zu Timeouts und
  verspaeteten Antworten ("Ignoriere Antwort mit fremder id") gefuehrt hat.
- Verspaetete Antworten werden vor jeder neuen Anfrage aus dem Empfangspuffer
  geworfen.
- `poll_enabled` steht wieder standardmaessig auf `true`, da die Intervalle
  jetzt einzeln steuerbar sind.

## 0.0.20 - 2026-09-28

- Die Initialisierung bricht beim ersten Timeout sofort ab, statt die
  restlichen Schritte ebenfalls ins Leere laufen zu lassen. Danach wartet die
  Bridge die doppelte `cd_time` und beginnt von vorn. Hintergrund: der Speicher
  schliesst seinen UDP-Port, wenn im Passive-Modus keine Kommandos mehr kommen.
- Eine Fehlerantwort des Geraets (JSON-RPC-Error) bricht nicht ab - nur
  ausbleibende Antworten.
- Nach `watchdog_failure_threshold` Abbruechen in Folge meldet der
  Health-Endpoint unhealthy und der Supervisor startet das Add-on neu.
- *Communication established* hat einen dritten Zustand `INIT`: Bridge startet
  bzw. wartet auf das Geraet. `FAIL` bleibt dem ausgeloesten Watchdog
  vorbehalten.
- `poll_enabled` steht jetzt standardmaessig auf `false`. Das zyklische Polling
  bleibt erhalten, wird aber meist nicht gebraucht, wenn die Abfragen ueber die
  Refresh-Buttons aus Home Assistant angestossen werden.

## 0.0.19 - 2026-09-28

- Das Log-Level `calc` wird in Pink statt dunklem Magenta ausgegeben. Auf
  dunklem Hintergrund war die bisherige Farbe schlecht lesbar.

## 0.0.18 - 2026-09-28

- Neues Log-Level `calc` zwischen `debug` und `info`. Es zeigt zusaetzlich zu
  `info` die Rechenwege der Bridge, ohne das Protokoll-Rauschen von `debug`:
  Regelschritte, Keepalive, Totband- und Deckel-Eingriffe, die automatischen
  `ES.SetMode`-Kommandos und die PV-Summenbildung.
- Neue Zeile "Rechnung: ..." pro Regelschritt mit allen Zwischenwerten -
  gemessener Wert, abgezogene Totzeit, Lage zum Halteband, Schrittgroesse samt
  Begruendung, alter und neuer Sollwert.
- Die genannten Meldungen liegen damit nicht mehr auf `debug`.

## 0.0.17 - 2026-09-26

- Halteband statt fester Zielwert: zwischen `self_regulation_band_low` (neu,
  Standard 0 W) und `self_regulation_reserve` wird nicht mehr gegengeregelt.
  Bisher hat die Bridge auch bei einem Netzbezug *unterhalb* der Reserve die
  Leistung zurueckgenommen, obwohl der Zustand besser war als das Ziel.
- Ausserhalb des Bands wird weiterhin auf die Reserve zurueckgeregelt, nach
  oben gebremst und nach unten in voller Hoehe.
- Die INFO-Zeile nennt das Halteband und vermerkt, wenn ein Wert darin liegt.

## 0.0.16 - 2026-09-26

- Eine Senkung der Obergrenze *Passive power* wirkt jetzt sofort: liegt der
  Sollwert darueber, wird er unmittelbar gekappt und gesendet. Bisher schickte
  der Keepalive bis zu `cd_time` Sekunden lang weiter die alte, zu hohe
  Leistung.
- Jedes ausgehende Passive-Kommando prueft den Sollwert zusaetzlich gegen den
  aktuellen Deckel - auch das des Keepalives.
- Wird der Deckel angehoben, plant die Bridge den zuletzt empfangenen Regelwert
  fuer den naechsten Schritt ein, damit der neue Spielraum genutzt wird.

## 0.0.15 - 2026-09-26

- Neue Option `restore_state` (Standard aktiv): Deckel, Countdown, Schalter der
  Selbstregelung, vorgemerkter Modus und zuletzt berechneter Sollwert werden in
  `/data/marstek_state.json` gesichert und nach einem Neustart wieder
  uebernommen. Bisher fiel der Deckel auf `passive_power_default` zurueck und
  die Regelung begann bei 0 W.
- Meldet das Geraet beim ersten `ES.GetMode` noch den Passive-Modus, wird
  dessen gemessene Leistung (`ongrid_power`) als Startwert verwendet - auf den
  Deckel begrenzt.
- Der Simulator merkt sich den zuletzt gesetzten Modus und meldet ihn in
  `ES.GetMode`, damit der Wiederanlauf testbar ist.

## 0.0.14 - 2026-09-26

**Fix:** Lag der berechnete Sollwert am Deckel, aber weniger als
`self_regulation_deadband` ueber dem aktuellen Wert, wurde er nie gesendet -
der Regler blieb dauerhaft knapp unter dem Deckel haengen, obwohl noch eine
grosse Abweichung offen war.

- Das Totband wird uebersprungen, sobald die Berechnung begrenzt wurde: am
  Deckel nach oben und bei 0 W nach unten. Abseits der Anschlaege wirkt es
  unveraendert.

## 0.0.13 - 2026-09-26

**Fix:** Bei negativem Netzwert (Einspeisung) hat der Regler denselben Fehler
mehrfach ausgeregelt und den Sollwert dabei bis auf 0 W heruntergezogen, was
zu einem Aufschaukeln der Regelung fuehrte.

- Totzeit-Kompensation: die zuletzt befohlene Aenderung wird als "in der
  Messung noch nicht sichtbar" vom Fehler abgezogen und verfaellt linear ueber
  die neue Option `self_regulation_settle_time` (Standard 10 s).
- Warnung beim Start, wenn `settle_time` groesser als `min_interval` ist.
- Neue Option `self_regulation_min_interval_down` (Standard 5 s): auch ein
  Fast-Down haelt einen Mindestabstand ein. Uebersprungen werden weiterhin das
  Totband und der laengere Aufwaerts-Takt.

## 0.0.12 - 2026-09-26

- Jede empfangene MQTT-Regelnachricht wird auf Log-Level `info` protokolliert,
  zusammen mit dem daraus berechneten Sollwert, dem aktuellen Sollwert und dem
  Deckel - auch dann, wenn anschliessend kein Kommando gesendet wird.
- Die Folgemeldungen automatischer Sendungen (`ES.SetMode`, Sendebestaetigung,
  Totband, Fast-Down) liegen jetzt auf `debug`, damit die INFO-Ebene bei
  aktiver Regelung genau eine Zeile pro Nachricht zeigt.

## 0.0.11 - 2026-09-26

**Achtung:** `self_regulation_mode` entfaellt. Die Regelung arbeitet jetzt
immer mit der Netzleistung als Eingang.

- Asymmetrische Regelung: nach oben gebremst (Anteil der Abweichung ueber
  `self_regulation_step_gain`, hoechstens `self_regulation_step_up` Watt),
  nach unten in voller Hoehe.
- `self_regulation_fast_down`: ein Schritt nach unten ueberspringt Totband und
  Mindestabstand, damit ein Lastabfall sofort ausgeregelt wird.
- `self_regulation_step_down` begrenzt bei Bedarf auch die Absenkung.
- `self_regulation_input_timeout` (Standard 60 s): bleiben Regelwerte aus,
  faellt der Sollwert auf 0 W statt vom Keepalive endlos weitergesendet zu
  werden.
- `self_regulation_min_interval` Standard von 2 auf 5 Sekunden erhoeht.

## 0.0.10 - 2026-09-26

- Eigener PV-Energiezaehler **PV energy (calculated)** im Geraet *Marstek
  Energy Status*: Integral ueber `pv_power` nach der Trapezregel mit der
  tatsaechlich vergangenen Zeit zwischen zwei `ES.GetStatus`-Antworten.
  Unabhaengig vom fehlerhaften `total_pv_energy` des Geraets.
- Der Zaehlerstand wird in `/data/marstek_state.json` gesichert und ueberlebt
  Neustarts des Add-ons.
- Neue Optionen `pv_energy_enabled` und `pv_energy_max_gap` (Standard 300 s):
  laengere Luecken zwischen zwei Messwerten werden verworfen statt
  hochgerechnet.

## 0.0.9 - 2026-09-26

- Die Entity *Communication established* wird als `enum` mit den Zustaenden
  `ON` und `FAIL` veroeffentlicht. Home Assistant bietet beide jetzt im
  Dropdown von Automationen und Bedingungen an, statt nur "Nicht verfuegbar"
  und "Unbekannt".

## 0.0.8 - 2026-09-25

- Selbstregelung fuer den Passive-Modus: die Bridge abonniert ein Topic mit
  einem gefilterten Regelwert und berechnet daraus die gesendete Leistung.
- Die Number-Entity *Passive power* wirkt bei aktiver Selbstregelung als
  Obergrenze, nach unten wird bei 0 W begrenzt (keine Einspeisung ins Netz).
- Konfigurierbare Reserve (Standard 12 W), Totband und minimaler Sendeabstand.
- Zwei Regelarten: `setpoint` (Wert direkt uebernehmen) und `grid` (Netzwert
  auf den bisherigen Sollwert aufsummieren).
- Der Keepalive laeuft bei aktiver Selbstregelung immer und startet den
  Countdown des Geraets neu, wenn keine neuen Werte eintreffen.
- Neue Entities: Switch *Self-regulation*, Sensoren *Regulation input* und
  *Regulation output*.

## 0.0.7 - 2026-09-25

- Die komplette Logzeile wird jetzt in der Farbe ihres Levels ausgegeben,
  inklusive Zeitstempel und Logger-Name. Hervorhebungen innerhalb einer
  Meldung bleiben erhalten.
- Neue Option `log_full_line_color` in der Gruppe `logging`, um auf die
  bisherige Darstellung (nur farbige Akzente) zurueckzuschalten.

## 0.0.6 - 2026-09-25

**Achtung: geaenderte Konfigurationsstruktur.** Nach dem Update einmal die
Add-on Konfiguration oeffnen und speichern.

- Optionen sind jetzt nach Themen gruppiert: `marstek_network_settings`,
  `mqtt_settings`, `message_settings`, `additions_status_requests`,
  `passiv_mode_settings`, `general_settings`, `logging`.
- Alte, flach abgelegte Optionen werden beim Laden weiterhin akzeptiert.
- `ble_mac` und `device_type` werden in die passende Gruppe zurueckgeschrieben.

## 0.0.5 - 2026-09-25

- Eigener Refresh-Button je Statusgruppe: *Marstek Battery*, *Marstek PV
  Status*, *Marstek Energy Status*, *Marstek Energy Mode* und (wenn aktiviert)
  *Marstek Energy Meter*. Der Button schickt genau die Abfrage dieser Gruppe
  erneut an das Geraet.

## 0.0.4 - 2026-09-25

- `ble_block_payload_invert` entfernt. `Ble.Adv` sendet fest `enable: 0` zum
  Sperren und `enable: 1` zum Freigeben, wie im Doku-Beispiel.

## 0.0.3 - 2026-09-25

- Beschreibungen fuer alle Optionen in der Add-on-Konfiguration
  (`translations/de.yaml` und `translations/en.yaml`).
- `ups_mode_string` entfernt - der UPS-Modus wird fest als `"UPS"` gesendet.
- `ble_block_invert` in `ble_block_payload_invert` umbenannt. Die Option kippt
  ausschliesslich den Payload von `Ble.Adv` und hat nichts mit Leistungswerten
  zu tun.

## 0.0.2 - 2026-09-25

- **Fix:** `image: null` aus der `config.yaml` entfernt. Der Supervisor konnte
  die Datei dadurch nicht einlesen und hat das Add-on nicht im Store angezeigt.
- Veraltete `arch`-Werte (`armhf`, `armv7`, `i386`) entfernt.
- Nicht benoetigtes `map: addon_config` entfernt.

## 0.0.1 - 2026-09-20

Erste Version.

- Lokale Marstek UDP Open API (Rev 2.0) als MQTT-Bridge mit Auto-Discovery.
- Initialisierungssequenz: `Marstek.GetDevice`, `Wifi.GetStatus`,
  `Bat.GetStatus`, `PV.GetStatus`, `ES.GetStatus`, `BLE.GetStatus`,
  `DOD.SET`, `Ble.Adv`, `Led.Ctrl`, `ES.GetMode` (optional `EM.GetStatus`).
- Gerätegruppen: Marstek System, Marstek Battery, Marstek PV Status,
  Marstek Energy Status, Marstek Energy Mode, Marstek Energy Control,
  Marstek Energy Meter (optional).
- Modussteuerung `Auto` / `AI` / `Passive` / `UPS` über Select + Apply-Button,
  Passive mit konfigurierbarer Leistung (-1200…1200 W) und Countdown (max 300 s,
  Default 10 s).
- Laufende Message-ID 0-999, eigene Instance-ID je Methode.
- Konfigurierbare Pause, Timeout, Retries und maximales Zeitfenster;
  `retries = 0` verwirft ohne Watchdog.
- Watchdog über Health-Endpoint (`/health`, `/status`) plus Status-Entity
  „Communication established" (ON / FAIL).
- `device_ble_mac` und `device_type` werden nach dem ersten Auslesen
  zurückgeschrieben.
- Konfigurierbare Log-Level mit ANSI-Farben.
