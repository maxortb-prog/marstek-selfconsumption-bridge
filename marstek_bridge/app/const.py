"""Zentrale Konstanten der Bridge."""

from __future__ import annotations

# --------------------------------------------------------------------------
# API Methoden (Marstek Device Open API, Rev 2.0)
# --------------------------------------------------------------------------
M_GET_DEVICE = "Marstek.GetDevice"
M_WIFI_STATUS = "Wifi.GetStatus"
M_BLE_STATUS = "BLE.GetStatus"
M_BAT_STATUS = "Bat.GetStatus"
M_PV_STATUS = "PV.GetStatus"
M_ES_STATUS = "ES.GetStatus"
M_ES_MODE = "ES.GetMode"
M_ES_SET_MODE = "ES.SetMode"
M_EM_STATUS = "EM.GetStatus"
M_DOD_SET = "DOD.SET"
M_BLE_ADV = "Ble.Adv"
M_LED_CTRL = "Led.Ctrl"

# --------------------------------------------------------------------------
# Instance-IDs ("params.id")
#
# Die Marstek Doku spricht durchgaengig von "ID of Instance" und verwendet in
# allen Beispielen 0. Laut Anforderung bekommt jede einzelne Abfrage eine
# eigene, fest zugeordnete Instance-Nummer. Wer das auf 0 zurueckdrehen will,
# setzt hier einfach ueberall 0 ein.
# --------------------------------------------------------------------------
INSTANCE_IDS: dict[str, int] = {
    M_GET_DEVICE: 0,
    M_WIFI_STATUS: 1,
    M_BLE_STATUS: 2,
    M_BAT_STATUS: 3,
    M_PV_STATUS: 4,
    M_ES_STATUS: 5,
    M_ES_MODE: 6,
    M_ES_SET_MODE: 7,
    M_EM_STATUS: 8,
    M_DOD_SET: 9,
    M_BLE_ADV: 10,
    M_LED_CTRL: 11,
}

# Laufende Message-ID ("id" auf Root-Ebene): 0..999, danach wieder 0.
MSG_ID_MIN = 0
MSG_ID_MAX = 999

# --------------------------------------------------------------------------
# Geraetegruppen in Home Assistant
# --------------------------------------------------------------------------
GRP_SYSTEM = "system"
GRP_BATTERY = "battery"
GRP_PV = "pv"
GRP_ENERGY_STATUS = "energy_status"
GRP_ENERGY_MODE = "energy_mode"
GRP_ENERGY_CONTROL = "energy_control"
GRP_ENERGY_METER = "energy_meter"

GROUP_TITLES: dict[str, str] = {
    GRP_SYSTEM: "Marstek System",
    GRP_BATTERY: "Marstek Battery",
    GRP_PV: "Marstek PV Status",
    GRP_ENERGY_STATUS: "Marstek Energy Status",
    GRP_ENERGY_MODE: "Marstek Energy Mode",
    GRP_ENERGY_CONTROL: "Marstek Energy Control",
    GRP_ENERGY_METER: "Marstek Energy Meter",
}

# --------------------------------------------------------------------------
# Betriebsmodi
# --------------------------------------------------------------------------
MODE_AUTO = "Auto"
MODE_AI = "AI"
MODE_PASSIVE = "Passive"
MODE_UPS = "UPS"

# "Manual" ist in der API vorhanden, benoetigt aber Zeitfenster-Parameter
# (time_num/start_time/end_time/week_set) und ist bewusst nicht Teil des
# Select-Entities.
SELECTABLE_MODES = [MODE_AUTO, MODE_AI, MODE_PASSIVE, MODE_UPS]

COMM_OK = "ON"
COMM_FAIL = "FAIL"
