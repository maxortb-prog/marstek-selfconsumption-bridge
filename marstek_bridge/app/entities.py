"""Definition aller Home-Assistant-Entities und der Discovery-Payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import __version__
from .const import GROUP_TITLES, GRP_SYSTEM, SELECTABLE_MODES

DIAG = "diagnostic"
CONF = "config"


def tpl(key: str) -> str:
    """Template, das bei fehlendem/leerem Wert den State unveraendert laesst."""
    return (
        "{%% if value_json.%(k)s is defined and value_json.%(k)s is not none %%}"
        "{{ value_json.%(k)s }}{%% endif %%}" % {"k": key}
    )


def bool_tpl(key: str) -> str:
    return (
        "{%% if value_json.%(k)s is defined and value_json.%(k)s is not none %%}"
        "{{ 'ON' if value_json.%(k)s else 'OFF' }}{%% endif %%}" % {"k": key}
    )


@dataclass
class Ent:
    """Beschreibung einer einzelnen Entity."""

    key: str
    name: str
    component: str = "sensor"
    device_class: str | None = None
    unit: str | None = None
    state_class: str | None = None
    icon: str | None = None
    category: str | None = None
    value_template: str | None = None
    command_suffix: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def template(self) -> str:
        if self.value_template is not None:
            return self.value_template
        if self.component == "binary_sensor":
            return bool_tpl(self.key)
        return tpl(self.key)


def refresh_button(label: str) -> Ent:
    """Button, der genau diese Statusabfrage erneut an das Geraet schickt."""
    return Ent(
        "refresh",
        f"Refresh {label}",
        component="button",
        icon="mdi:refresh",
        command_suffix="refresh",
        extra={"payload_press": "PRESS"},
    )


# ---------------------------------------------------------------------------
# Marstek System  (Marstek.GetDevice / Wifi.GetStatus / BLE.GetStatus
#                  + DOD / Ble_block / Led_Ctrl + Kommunikationsstatus)
# ---------------------------------------------------------------------------
SYSTEM_ENTITIES: list[Ent] = [
    Ent("communication", "Communication established", icon="mdi:lan-connect"),
    Ent(
        "comm_ok",
        "Device connectivity",
        component="binary_sensor",
        device_class="connectivity",
        category=DIAG,
    ),
    Ent("device", "Device type", icon="mdi:chip", category=DIAG),
    Ent("ver", "Firmware version", icon="mdi:tag-outline", category=DIAG),
    Ent("ip", "IP address", icon="mdi:ip-network", category=DIAG),
    Ent("ssid", "WiFi SSID", icon="mdi:wifi", category=DIAG),
    Ent(
        "rssi",
        "WiFi signal",
        device_class="signal_strength",
        unit="dBm",
        state_class="measurement",
        category=DIAG,
    ),
    Ent("wifi_mac", "WiFi MAC", icon="mdi:network-outline", category=DIAG),
    Ent("sta_gate", "Gateway", icon="mdi:router-network", category=DIAG),
    Ent("sta_mask", "Subnet mask", icon="mdi:ip-outline", category=DIAG),
    Ent("sta_dns", "DNS", icon="mdi:dns-outline", category=DIAG),
    Ent("ble_state", "Bluetooth state", icon="mdi:bluetooth", category=DIAG),
    Ent("ble_mac", "Bluetooth MAC", icon="mdi:bluetooth-settings", category=DIAG),
    Ent(
        "last_set_result",
        "Last set result",
        icon="mdi:check-decagram-outline",
        category=DIAG,
    ),
    Ent(
        "last_update",
        "Last update",
        device_class="timestamp",
        icon="mdi:clock-outline",
        category=DIAG,
    ),
    # --- steuerbare System-Entities ---
    Ent(
        "dod_value",
        "DOD",
        component="number",
        unit="%",
        icon="mdi:battery-arrow-down",
        category=CONF,
        command_suffix="dod",
        extra={"min": 30, "max": 88, "step": 1, "mode": "box"},
    ),
    Ent(
        "ble_block",
        "Bluetooth block",
        component="switch",
        icon="mdi:bluetooth-off",
        category=CONF,
        command_suffix="ble_block",
        value_template=bool_tpl("ble_block"),
    ),
    Ent(
        "led_state",
        "LED",
        component="switch",
        icon="mdi:led-on",
        category=CONF,
        command_suffix="led",
        value_template=bool_tpl("led_state"),
    ),
]

# ---------------------------------------------------------------------------
# Marstek Battery  (Bat.GetStatus)
# ---------------------------------------------------------------------------
BATTERY_ENTITIES: list[Ent] = [
    Ent("soc", "Battery SOC", device_class="battery", unit="%", state_class="measurement"),
    Ent(
        "bat_temp",
        "Battery temperature",
        device_class="temperature",
        unit="°C",
        state_class="measurement",
    ),
    Ent(
        "bat_capacity",
        "Battery remaining capacity",
        device_class="energy_storage",
        unit="Wh",
        state_class="measurement",
    ),
    Ent(
        "rated_capacity",
        "Battery rated capacity",
        device_class="energy_storage",
        unit="Wh",
        state_class="measurement",
        category=DIAG,
    ),
    Ent(
        "charg_flag",
        "Charging allowed",
        component="binary_sensor",
        icon="mdi:battery-plus-outline",
    ),
    Ent(
        "dischrg_flag",
        "Discharging allowed",
        component="binary_sensor",
        icon="mdi:battery-minus-outline",
    ),
    refresh_button("battery status"),
]

# ---------------------------------------------------------------------------
# Marstek PV Status  (PV.GetStatus)
#
# Die Doku beschreibt pv_power/pv_voltage/pv_current/pv_state, das Beispiel
# liefert aber pv1..pv4. Deshalb werden die Entities aus der ersten echten
# Antwort erzeugt - es entstehen nur Entities fuer tatsaechlich vorhandene
# Strings.
# ---------------------------------------------------------------------------
_PV_STATE_TPL = (
    "{%% if value_json.%(k)s is defined and value_json.%(k)s is not none %%}"
    "{{ 'Work' if value_json.%(k)s|int == 1 else 'Standby' }}{%% endif %%}"
)


def build_pv_entities(sample: dict[str, Any]) -> list[Ent]:
    """PV-Entities anhand der tatsaechlich gelieferten Keys erzeugen."""
    ents: list[Ent] = []
    for key in sorted(k for k in sample if not k.startswith("_") and k != "id"):
        low = key.lower()
        label = key.replace("_", " ").replace("pv", "PV").strip()
        if low.endswith("_power"):
            ents.append(
                Ent(
                    key,
                    f"{_pv_label(key)} power",
                    device_class="power",
                    unit="W",
                    state_class="measurement",
                )
            )
        elif low.endswith("_voltage"):
            ents.append(
                Ent(
                    key,
                    f"{_pv_label(key)} voltage",
                    device_class="voltage",
                    unit="V",
                    state_class="measurement",
                )
            )
        elif low.endswith("_current"):
            ents.append(
                Ent(
                    key,
                    f"{_pv_label(key)} current",
                    device_class="current",
                    unit="A",
                    state_class="measurement",
                )
            )
        elif low.endswith("_state"):
            ents.append(
                Ent(
                    key,
                    f"{_pv_label(key)} state",
                    icon="mdi:solar-power-variant",
                    value_template=_PV_STATE_TPL % {"k": key},
                )
            )
        else:
            ents.append(Ent(key, label, category=DIAG))
    ents.append(refresh_button("PV status"))
    return ents


def _pv_label(key: str) -> str:
    head = key.split("_", 1)[0]
    if head.lower().startswith("pv") and head[2:].isdigit():
        return f"PV{head[2:]}"
    return "PV"


# ---------------------------------------------------------------------------
# Marstek Energy Status  (ES.GetStatus)
# ---------------------------------------------------------------------------
ENERGY_STATUS_ENTITIES: list[Ent] = [
    Ent("bat_soc", "Total battery SOC", device_class="battery", unit="%", state_class="measurement"),
    Ent(
        "bat_cap",
        "Total battery capacity",
        device_class="energy_storage",
        unit="Wh",
        state_class="measurement",
    ),
    Ent("pv_power", "Solar charging power", device_class="power", unit="W", state_class="measurement"),
    Ent("ongrid_power", "Grid-tied power", device_class="power", unit="W", state_class="measurement"),
    Ent("offgrid_power", "Off-grid power", device_class="power", unit="W", state_class="measurement"),
    Ent("bat_power", "Battery power", device_class="power", unit="W", state_class="measurement"),
    Ent(
        "total_pv_energy",
        "Total solar energy",
        device_class="energy",
        unit="Wh",
        state_class="total_increasing",
    ),
    Ent(
        "total_grid_output_energy",
        "Total grid output energy",
        device_class="energy",
        unit="Wh",
        state_class="total_increasing",
    ),
    Ent(
        "total_grid_input_energy",
        "Total grid input energy",
        device_class="energy",
        unit="Wh",
        state_class="total_increasing",
    ),
    Ent(
        "total_load_energy",
        "Total load energy",
        device_class="energy",
        unit="Wh",
        state_class="total_increasing",
    ),
    refresh_button("energy status"),
]

# ---------------------------------------------------------------------------
# Marstek Energy Mode  (ES.GetMode)
# ---------------------------------------------------------------------------
ENERGY_MODE_ENTITIES: list[Ent] = [
    Ent("mode", "Operating mode", icon="mdi:state-machine"),
    Ent("ongrid_power", "Grid-tied power", device_class="power", unit="W", state_class="measurement"),
    Ent("offgrid_power", "Off-grid power", device_class="power", unit="W", state_class="measurement"),
    Ent("bat_soc", "Battery SOC", device_class="battery", unit="%", state_class="measurement"),
    Ent(
        "ct_state",
        "CT connected",
        component="binary_sensor",
        device_class="connectivity",
        value_template=(
            "{% if value_json.ct_state is defined and value_json.ct_state is not none %}"
            "{{ 'ON' if value_json.ct_state|int == 1 else 'OFF' }}{% endif %}"
        ),
    ),
    Ent("a_power", "Phase A power", device_class="power", unit="W", state_class="measurement"),
    Ent("b_power", "Phase B power", device_class="power", unit="W", state_class="measurement"),
    Ent("c_power", "Phase C power", device_class="power", unit="W", state_class="measurement"),
    Ent("total_power", "CT total power", device_class="power", unit="W", state_class="measurement"),
    Ent(
        "input_energy",
        "Cumulative input energy",
        device_class="energy",
        unit="Wh",
        state_class="total_increasing",
    ),
    Ent(
        "output_energy",
        "Cumulative output energy",
        device_class="energy",
        unit="Wh",
        state_class="total_increasing",
    ),
    refresh_button("energy mode"),
]

# ---------------------------------------------------------------------------
# Marstek Energy Meter  (EM.GetStatus, optional)
# ---------------------------------------------------------------------------
ENERGY_METER_ENTITIES: list[Ent] = [
    Ent(
        "ct_state",
        "CT connected",
        component="binary_sensor",
        device_class="connectivity",
        value_template=(
            "{% if value_json.ct_state is defined and value_json.ct_state is not none %}"
            "{{ 'ON' if value_json.ct_state|int == 1 else 'OFF' }}{% endif %}"
        ),
    ),
    Ent("a_power", "Phase A power", device_class="power", unit="W", state_class="measurement"),
    Ent("b_power", "Phase B power", device_class="power", unit="W", state_class="measurement"),
    Ent("c_power", "Phase C power", device_class="power", unit="W", state_class="measurement"),
    Ent("total_power", "Total power", device_class="power", unit="W", state_class="measurement"),
    Ent(
        "input_energy",
        "Cumulative input energy",
        device_class="energy",
        unit="Wh",
        state_class="total_increasing",
    ),
    Ent(
        "output_energy",
        "Cumulative output energy",
        device_class="energy",
        unit="Wh",
        state_class="total_increasing",
    ),
    refresh_button("energy meter"),
]


# ---------------------------------------------------------------------------
# Marstek Energy Control  (ES.SetMode)
# ---------------------------------------------------------------------------
def build_control_entities(
    power_min: int, power_max: int, cd_max: int
) -> list[Ent]:
    return [
        Ent(
            "target_mode",
            "Mode selection",
            component="select",
            icon="mdi:format-list-bulleted",
            command_suffix="mode",
            extra={"options": list(SELECTABLE_MODES)},
        ),
        Ent(
            "apply",
            "Apply mode",
            component="button",
            icon="mdi:send-check-outline",
            command_suffix="apply",
            extra={"payload_press": "PRESS"},
        ),
        Ent(
            "passive_power",
            "Passive power",
            component="number",
            device_class="power",
            unit="W",
            icon="mdi:transmission-tower",
            command_suffix="passive_power",
            extra={
                "min": power_min,
                "max": power_max,
                "step": 1,
                "mode": "box",
            },
        ),
        Ent(
            "passive_cd_time",
            "Passive countdown",
            component="number",
            device_class="duration",
            unit="s",
            icon="mdi:timer-outline",
            command_suffix="passive_cd_time",
            extra={"min": 0, "max": cd_max, "step": 1, "mode": "box"},
        ),
        Ent(
            "refresh",
            "Refresh data",
            component="button",
            icon="mdi:refresh",
            category=DIAG,
            command_suffix="refresh",
            extra={"payload_press": "PRESS"},
        ),
        Ent("applied_mode", "Last applied mode", icon="mdi:history", category=DIAG),
        Ent(
            "self_regulation",
            "Self-regulation",
            component="switch",
            icon="mdi:auto-mode",
            command_suffix="self_regulation",
            value_template=bool_tpl("self_regulation"),
        ),
        Ent(
            "regulation_input",
            "Regulation input",
            device_class="power",
            unit="W",
            state_class="measurement",
            icon="mdi:import",
        ),
        Ent(
            "regulation_output",
            "Regulation output",
            device_class="power",
            unit="W",
            state_class="measurement",
            icon="mdi:export",
        ),
    ]


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
class DiscoveryBuilder:
    """Baut Discovery-Topics und -Payloads."""

    def __init__(
        self,
        *,
        uid: str,
        base_topic: str,
        discovery_prefix: str,
        availability_topic: str,
        area: str | None,
        model: str,
        sw_version: str,
        config_url: str | None = None,
    ) -> None:
        self.uid = uid
        self.base_topic = base_topic.strip("/")
        self.discovery_prefix = discovery_prefix.strip("/")
        self.availability_topic = availability_topic
        self.area = area or None
        self.model = model or "Marstek"
        self.sw_version = sw_version
        self.config_url = config_url

    # ------------------------------------------------------------------
    def state_topic(self, group: str) -> str:
        return f"{self.base_topic}/{group}/state"

    def command_topic(self, group: str, suffix: str) -> str:
        return f"{self.base_topic}/{group}/{suffix}/set"

    def node_id(self, group: str) -> str:
        return f"marstek_{self.uid}_{group}"

    # ------------------------------------------------------------------
    def device_block(self, group: str) -> dict[str, Any]:
        block: dict[str, Any] = {
            "identifiers": [self.node_id(group)],
            "name": GROUP_TITLES[group],
            "manufacturer": "Marstek",
            "model": self.model,
            "sw_version": f"{self.sw_version} (bridge {__version__})",
        }
        if self.area:
            block["suggested_area"] = self.area
        if self.config_url:
            block["configuration_url"] = self.config_url
        if group != GRP_SYSTEM:
            block["via_device"] = self.node_id(GRP_SYSTEM)
        return block

    # ------------------------------------------------------------------
    def build(self, group: str, ent: Ent) -> tuple[str, dict[str, Any]]:
        object_id = f"marstek_{self.uid}_{group}_{ent.key}"
        topic = (
            f"{self.discovery_prefix}/{ent.component}/"
            f"{self.node_id(group)}/{ent.key}/config"
        )
        payload: dict[str, Any] = {
            "name": ent.name,
            "unique_id": object_id,
            "object_id": object_id,
            "availability_topic": self.availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": self.device_block(group),
            "qos": 0,
        }
        if ent.component != "button":
            payload["state_topic"] = self.state_topic(group)
            payload["value_template"] = ent.template()
        if ent.device_class:
            payload["device_class"] = ent.device_class
        if ent.unit:
            payload["unit_of_measurement"] = ent.unit
        if ent.state_class:
            payload["state_class"] = ent.state_class
        if ent.icon:
            payload["icon"] = ent.icon
        if ent.category:
            payload["entity_category"] = ent.category
        if ent.command_suffix:
            payload["command_topic"] = self.command_topic(group, ent.command_suffix)
        if ent.component == "switch":
            payload.update({"payload_on": "ON", "payload_off": "OFF"})
        payload.update(ent.extra)
        return topic, payload
