# Changelog

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
