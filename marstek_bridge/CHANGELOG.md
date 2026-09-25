# Changelog

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
