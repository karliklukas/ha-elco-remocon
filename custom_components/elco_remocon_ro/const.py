"""Constants and the list of values read from the Remocon-Net cloud."""

from __future__ import annotations

from dataclasses import dataclass, field

DOMAIN = "elco_remocon_ro"
MANUFACTURER = "ELCO"

CONF_API_URL = "api_url"
CONF_GATEWAY = "gateway"
CONF_PLANT_NAME = "plant_name"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 120  # seconds
ENERGY_SCAN_INTERVAL = 30 * 60  # consumption reports change every 2 hours
MIN_SCAN_INTERVAL = 60
# the cloud localizes dataItems enum texts by "culture"; follow the Home Assistant language
# (verified 2026-11-01: cs-CZ / de-DE / en-US are localized, an unknown culture falls back to English)
CULTURES = {"cs": "cs-CZ", "de": "de-DE", "en": "en-US"}
DEFAULT_CULTURE = "en-US"
DEFAULT_TITLES = {"cs": "Tepelné čerpadlo", "de": "Wärmepumpe", "en": "Heat pump"}

SOURCE_DATA = "di"  # named dataItems (remote/dataItems/{gw}/get)
SOURCE_MENU = "mi"  # numbered menuItems (menuItems/{gw}?menuItems=...)


@dataclass(frozen=True)
class ItemDef:
    """One value read from the cloud and exposed as an entity."""

    source: str  # SOURCE_DATA / SOURCE_MENU
    key: str | int  # dataItem id or menuItem number
    platform: str  # "sensor" | "binary_sensor"
    translation_key: str  # entity name (and enum states) in translations/*.json
    zone: int = 0  # dataItems only
    device_class: str | None = None
    unit: str | None = None
    state_class: str | None = None  # "measurement" for real measurements only
    kind: str = "number"  # "number" | "text" (enum -> text) | "bool"
    icon: str | None = None
    enabled: bool = True
    diagnostic: bool = False
    text_map: dict[int, str] = field(default_factory=dict)  # value -> enum state key (translated in translations/*.json)

    @property
    def options(self) -> list[str]:
        """Enum states (unique, in value order) for an item with a text_map."""
        return list(dict.fromkeys(self.text_map.values()))


# Heat pump operating state (menuItem 340, controller node T_13.9.0) -> enum state key.
HP_MODES = {
    0: "off",
    1: "standby",
    2: "cooling",
    3: "heating",
    4: "heating_booster",
    5: "cooling_booster",
    6: "test_heating",
    7: "test_cooling",
    8: "frost_protection",
    9: "defrost",
    10: "overheat_protection",
    11: "compressor_delay",
    12: "system_fault",
    13: "severe_system_fault",
    14: "refrigerant_pump_down",
    15: "emergency",
    16: "fan_test",
    17: "defrost",
    18: "cascade_heating",
    19: "cascade_cooling",
}

# HV input 1 function (menuItem 303) -> enum state key.
HV_INPUT_FUNCTIONS = {
    0: "undefined",
    1: "unused",
    2: "edf",
    3: "sg_ready_1",
    4: "external_off",
    5: "pv_integration",
}

TEMP = "temperature"
C = "°C"
M = "measurement"

ITEMS: list[ItemDef] = [
    # --- states (binary) ---------------------------------------------------------------
    ItemDef(SOURCE_DATA, "IsHeatingPumpOn", "binary_sensor", "hp_running", device_class="running", kind="bool", icon="mdi:heat-pump"),
    ItemDef(SOURCE_DATA, "IsResistorOn", "binary_sensor", "dhw_heating_rod", device_class="running", kind="bool", icon="mdi:heating-coil"),
    ItemDef(SOURCE_MENU, 337, "binary_sensor", "ch_backup_heater", device_class="running", kind="bool", icon="mdi:heating-coil"),
    ItemDef(SOURCE_DATA, "IsDhwBoost", "binary_sensor", "dhw_boost", kind="bool", icon="mdi:water-boiler-alert"),
    ItemDef(SOURCE_DATA, "IsQuite", "binary_sensor", "quiet_mode", kind="bool", icon="mdi:volume-off"),
    ItemDef(SOURCE_DATA, "ZoneHeatRequest", "binary_sensor", "heat_request", zone=1, kind="bool", icon="mdi:radiator"),
    ItemDef(SOURCE_DATA, "Holiday", "binary_sensor", "holiday", kind="bool", icon="mdi:palm-tree"),
    ItemDef(SOURCE_DATA, "AutomaticThermoregulation", "binary_sensor", "weather_compensation", kind="bool", icon="mdi:sun-thermometer", diagnostic=True),
    ItemDef(SOURCE_MENU, 304, "binary_sensor", "hv_input_1", kind="bool", icon="mdi:electric-switch", diagnostic=True),
    # --- heat pump -----------------------------------------------------------------------
    ItemDef(SOURCE_MENU, 340, "sensor", "hp_mode", kind="text", icon="mdi:heat-pump-outline", text_map=HP_MODES),
    ItemDef(SOURCE_MENU, 348, "sensor", "hp_water_temperature", device_class=TEMP, unit=C, state_class=M),
    ItemDef(SOURCE_MENU, 349, "sensor", "ch_flow_temperature", device_class=TEMP, unit=C, state_class=M),
    ItemDef(SOURCE_DATA, "ChFlowSetpointTemp", "sensor", "ch_flow_setpoint", device_class=TEMP, unit=C),
    ItemDef(SOURCE_DATA, "HeatingCircuitPressure", "sensor", "system_pressure", device_class="pressure", unit="bar", state_class=M),
    # --- outdoor -------------------------------------------------------------------------
    ItemDef(SOURCE_DATA, "OutsideTemp", "sensor", "outdoor_temperature", device_class=TEMP, unit=C, state_class=M),
    ItemDef(SOURCE_MENU, 341, "sensor", "outdoor_temperature_hp", device_class=TEMP, unit=C, state_class=M),
    ItemDef(SOURCE_MENU, 130, "sensor", "outdoor_temperature_online", device_class=TEMP, unit=C, state_class=M, enabled=False),
    # --- room / zone 1 -------------------------------------------------------------------
    ItemDef(SOURCE_DATA, "ZoneMeasuredTemp", "sensor", "room_temperature", zone=1, device_class=TEMP, unit=C, state_class=M),
    ItemDef(SOURCE_MENU, 146, "sensor", "room_humidity", device_class="humidity", unit="%", state_class=M),
    ItemDef(SOURCE_DATA, "ZoneDesiredTemp", "sensor", "room_target_temperature", zone=1, device_class=TEMP, unit=C),
    ItemDef(SOURCE_DATA, "ZoneComfortTemp", "sensor", "room_comfort_temperature", zone=1, device_class=TEMP, unit=C),
    ItemDef(SOURCE_DATA, "ZoneEconomyTemp", "sensor", "room_economy_temperature", zone=1, device_class=TEMP, unit=C),
    ItemDef(SOURCE_DATA, "ZoneMode", "sensor", "zone_mode", zone=1, kind="text", icon="mdi:calendar-clock"),
    ItemDef(SOURCE_DATA, "HeatingFlowOffset", "sensor", "heating_curve_offset", zone=1, icon="mdi:chart-bell-curve", diagnostic=True),
    # --- domestic hot water --------------------------------------------------------------
    ItemDef(SOURCE_DATA, "DhwStorageTemperature", "sensor", "dhw_tank_temperature", device_class=TEMP, unit=C, state_class=M),
    ItemDef(SOURCE_DATA, "DhwTemp", "sensor", "dhw_target_temperature", device_class=TEMP, unit=C),
    ItemDef(SOURCE_DATA, "DhwTimeProgComfortTemp", "sensor", "dhw_comfort_temperature", device_class=TEMP, unit=C),
    ItemDef(SOURCE_DATA, "DhwTimeProgEconomyTemp", "sensor", "dhw_economy_temperature", device_class=TEMP, unit=C),
    ItemDef(SOURCE_DATA, "DhwMode", "sensor", "dhw_mode", kind="text", icon="mdi:water-boiler"),
    # --- system / buffer -----------------------------------------------------------------
    ItemDef(SOURCE_DATA, "PlantMode", "sensor", "plant_mode", kind="text", icon="mdi:sun-snowflake-variant"),
    ItemDef(SOURCE_DATA, "BufferControlMode", "sensor", "buffer_mode", kind="text", icon="mdi:storage-tank"),
    ItemDef(SOURCE_DATA, "BufferTimeProgComfortHeatingTemp", "sensor", "buffer_comfort_temperature", device_class=TEMP, unit=C),
    ItemDef(SOURCE_DATA, "BufferTimeProgEconomyHeatingTemp", "sensor", "buffer_economy_temperature", device_class=TEMP, unit=C),
    # --- diagnostics ---------------------------------------------------------------------
    ItemDef(SOURCE_MENU, 303, "sensor", "hv_input_1_function", kind="text", icon="mdi:electric-switch", diagnostic=True, text_map=HV_INPUT_FUNCTIONS),
    ItemDef(SOURCE_MENU, 119, "sensor", "signal_strength", unit="%", state_class=M, icon="mdi:wifi", diagnostic=True),
]

# menuItems verified to work on a GALEVO / AEROTOP MONO.2 plant (probe 2026-10-13).
# Only these are requested - ONE unsupported number fails the whole request with HTTP 500.
# Known to crash the cloud (never request): 132, 306-335, 342-347, 310+ ranges outside the list.
MENU_IDS: list[int] = sorted({i.key for i in ITEMS if i.source == SOURCE_MENU})  # type: ignore[type-var]


def culture_for(language: str | None) -> str:
    """Cloud culture for a Home Assistant language ("de", "en-GB", ...); English when not supported."""
    return CULTURES.get((language or "").split("-")[0].lower(), DEFAULT_CULTURE)


def default_title(language: str | None) -> str:
    """Default device / config entry name in the Home Assistant language."""
    return DEFAULT_TITLES.get((language or "").split("-")[0].lower(), DEFAULT_TITLES["en"])


def data_item_request(zones: list[int]) -> list[dict[str, int | str]]:
    """Body 'items' for dataItems: every SOURCE_DATA id, zone-bound ones for each zone."""
    request: list[dict[str, int | str]] = []
    seen: set[tuple[str, int]] = set()
    for item in ITEMS:
        if item.source != SOURCE_DATA:
            continue
        for zn in ([0] if item.zone == 0 else zones):
            if (str(item.key), zn) not in seen:
                seen.add((str(item.key), zn))
                request.append({"id": str(item.key), "zn": zn})
    return request
