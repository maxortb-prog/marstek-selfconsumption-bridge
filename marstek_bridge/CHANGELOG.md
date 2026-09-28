# Changelog

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
