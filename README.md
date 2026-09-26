# Marstek for Self-consumption regulation (MQTT - UDP Bridge)

Home-Assistant-Add-on, das einen Marstek Speicher (Venus C/E/D/A) ueber die
**lokale UDP Open API (Rev 2.0)** anspricht und ihn per **MQTT Auto-Discovery**
vollstaendig in Home Assistant abbildet - inklusive Steuerung der
Betriebsmodi (`Auto`, `AI`, `Passive`, `UPS`) fuer die Eigenverbrauchsregelung.

> Die Local API wird von Marstek "as is" bereitgestellt. Nutzung auf eigenes
> Risiko. Dieses Projekt steht in keiner Verbindung zu Marstek.

---

## Installation in Home Assistant OS

1. **Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories**
2. URL dieses Repos eintragen:
   `https://github.com/maxortb-prog/marstek-selfconsumption-bridge`
3. Add-on **„Marstek Self-consumption Bridge"** installieren.
4. Auf dem Speicher muss die Open API in der Marstek-App aktiviert und der
   UDP-Port gesetzt sein (Default 30000, empfohlen 49152-65535).
5. Optionen ausfuellen (mindestens `device_ip`, MQTT-Zugangsdaten), starten.
6. **Watchdog** und **Start beim Booten** im Add-on einschalten.

Voraussetzung: ein MQTT-Broker (z. B. Add-on *Mosquitto broker*) und die
MQTT-Integration in Home Assistant.

---

## Was passiert beim Start

```
MQTT verbinden  ──►  Watchdog scharf (Health-Endpoint)
   │
   ├─ 1  Marstek.GetDevice   → Marstek System      (+ ble_mac/device_type sichern)
   ├─ 2  Wifi.GetStatus      → Marstek System
   ├─ 3  Bat.GetStatus       → Marstek Battery
   ├─ 4  PV.GetStatus        → Marstek PV Status
   ├─ 5  ES.GetStatus        → Marstek Energy Status
   ├─ 6  BLE.GetStatus       → Marstek System
   ├─ 7  DOD.SET   (88)      → Marstek System
   ├─ 8  Ble.Adv   (Block ON)→ Marstek System
   ├─ 9  Led.Ctrl  (OFF)     → Marstek System
   └─10  ES.GetMode          → Marstek Energy Mode
   (optional 11  EM.GetStatus → Marstek Energy Meter)
   │
   └──►  "Communication established" = ON
```

Zwischen allen Abfragen liegt `request_delay` (Default 1 s). Danach laeuft ein
zyklisches Polling (`poll_interval`, Default 30 s) ueber Battery, PV,
ES.GetStatus, ES.GetMode (+ EM).

---

## Geraetegruppen in Home Assistant

| Gerät | Quelle | Inhalt |
|---|---|---|
| **Marstek System** | `Marstek.GetDevice`, `Wifi.GetStatus`, `BLE.GetStatus`, `DOD.SET`, `Ble.Adv`, `Led.Ctrl` | Gerätetyp, Firmware, IP/SSID/RSSI/Gateway/DNS, BLE-Status, **Communication established**, DOD-Number, Switches für BLE-Block und LED |
| **Marstek Battery** | `Bat.GetStatus` | SOC, Temperatur, Rest-/Nennkapazität, Lade-/Entladefreigabe |
| **Marstek PV Status** | `PV.GetStatus` | Leistung, Spannung, Strom und Status je MPPT-String (Entities werden aus der echten Antwort erzeugt) |
| **Marstek Energy Status** | `ES.GetStatus` | SOC, Kapazität, PV-/Netz-/Insel-/Batterieleistung, Energiezähler |
| **Marstek Energy Mode** | `ES.GetMode` | aktiver Modus, Netz-/Inselleistung, CT-Status, Phasenleistungen, kumulierte Energien |
| **Marstek Energy Control** | `ES.SetMode` | Mode-Select, **Apply-Button**, Passive-Leistung, Passive-Countdown, Refresh-Button |
| **Marstek Energy Meter** *(optional)* | `EM.GetStatus` | CT-Daten, Phasen- und Gesamtleistung |

Alle Geräte bekommen `suggested_area` (Default `Marstek`) und hängen per
`via_device` an *Marstek System*.

---

## Modus umschalten

Das Select **Mode selection** merkt den Zielmodus nur vor - erst der Button
**Apply mode** sendet `ES.SetMode`. So lassen sich Passive-Leistung und
Countdown vorher setzen, ohne bei jeder Änderung ein Kommando abzufeuern.

```yaml
# Beispiel-Automation: 800 W ins Netz einspeisen
- service: number.set_value
  target: {entity_id: number.marstek_..._energy_control_passive_power}
  data: {value: 800}
- service: number.set_value
  target: {entity_id: number.marstek_..._energy_control_passive_cd_time}
  data: {value: 10}
- service: select.select_option
  target: {entity_id: select.marstek_..._energy_control_target_mode}
  data: {option: "Passive"}
- service: button.press
  target: {entity_id: button.marstek_..._energy_control_apply}
```

Vorzeichen: **positiv = Einspeisen/Entladen** (0 … `passive_power_max`),
**negativ = Laden** (`passive_power_min` … 0).

---

## Selbstregelung

Mit dem Switch **Self-regulation** regelt die Bridge im Passive-Modus auf einen
kleinen, konstanten Netzbezug (Standard 12 W) ein. Eingang ist die Netzleistung
auf einem MQTT-Topic.

```
Abweichung = Netzwert − Reserve
  > 0 (zu viel Bezug)  → Schritt = min(Abweichung × 0,5 , 50 W)   gebremst
  < 0 (zu wenig Bezug) → Schritt = Abweichung                     sofort, voll
Sollwert = clamp(Sollwert + Schritt, 0, "Passive power")
```

Nach oben wird gedämpft, damit der Regler nicht überschießt und ins Netz
einspeist; nach unten wird in voller Höhe und ohne Totband oder Wartezeit
korrigiert. Der Sollwert wird nie negativ. Bleiben Werte aus, fällt er nach
`self_regulation_input_timeout` auf 0 W. Details in
[DOCS.md](marstek_bridge/DOCS.md).

---

## Watchdog

* `request_retries = 0` → ein Versuch, Timeout wird **verworfen**, kein Watchdog.
* `request_retries > 0` → Wiederholungen; scheitern alle oder läuft
  `request_max_time` ab, wird der Watchdog ausgelöst:
  *Communication established* = **FAIL** und der Health-Endpoint
  (`http://<host>:8099/health`) liefert nach `watchdog_failure_threshold`
  aufeinanderfolgenden Fehlern HTTP 503 → der Supervisor startet das Add-on neu.
* Fällt MQTT aus, meldet der Health-Endpoint ebenfalls 503.
* `http://<host>:8099/status` liefert den Detailstatus als JSON.

Die Verfügbarkeit (`.../status` = `online`/`offline`) hängt am Add-on, nicht am
Speicher - dadurch bleibt der Zustand **FAIL** in HA sichtbar statt „unavailable".

---

## Lokal testen (ohne Speicher)

```bash
python3 tools/fake_marstek_device.py --port 30000            # Simulator
cd marstek_bridge
MARSTEK_DEVICE_IP=127.0.0.1 MARSTEK_MQTT_HOST=127.0.0.1 \
MARSTEK_MQTT_USERNAME= MARSTEK_MQTT_PASSWORD= \
MARSTEK_OPTIONS=/tmp/none.json MARSTEK_STATE=/tmp/state.json \
MARSTEK_LOG_LEVEL=trace python3 -m app.main
```

Jede Option lässt sich per `MARSTEK_<OPTION_IN_GROSSBUCHSTABEN>` überschreiben.

---

## Lizenz

MIT - siehe [LICENSE](LICENSE).
