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
MIN_SCAN_INTERVAL = 60
CULTURE = "cs-CZ"  # dataItems enum texts come localized

SOURCE_DATA = "di"  # named dataItems (remote/dataItems/{gw}/get)
SOURCE_MENU = "mi"  # numbered menuItems (menuItems/{gw}?menuItems=...)


@dataclass(frozen=True)
class ItemDef:
    """One value read from the cloud and exposed as an entity."""

    source: str  # SOURCE_DATA / SOURCE_MENU
    key: str | int  # dataItem id or menuItem number
    platform: str  # "sensor" | "binary_sensor"
    name: str
    zone: int = 0  # dataItems only
    device_class: str | None = None
    unit: str | None = None
    state_class: str | None = None  # "measurement" for real measurements only
    kind: str = "number"  # "number" | "text" (enum -> text) | "bool"
    icon: str | None = None
    enabled: bool = True
    diagnostic: bool = False
    text_map: dict[int, str] = field(default_factory=dict)  # value -> text override


# Heat pump operating state (menuItem 340, controller node T_13.9.0). Cloud texts are English.
HP_MODE_TEXTS = {
    0: "Vypnuto",
    1: "Pohotovost",
    2: "Chlazení",
    3: "Topení",
    4: "Topení s dohřevem",
    5: "Chlazení s posilou",
    6: "Zkušební topení",
    7: "Zkušební chlazení",
    8: "Ochrana proti mrazu",
    9: "Odmrazování",
    10: "Ochrana proti přehřátí",
    11: "Časová ochrana kompresoru",
    12: "Porucha systému",
    13: "Závažná porucha systému",
    14: "Odčerpání chladiva",
    15: "Nouzový režim",
    16: "Zkušební běh ventilátoru",
    17: "Odmrazování",
    18: "Kaskádové topení",
    19: "Kaskádové chlazení",
}

HV_INPUT_TEXTS = {
    0: "Nedefinováno",
    1: "Nepoužito",
    2: "EDF",
    3: "SG Ready 1",
    4: "Externí vypnutí",
    5: "Integrace FVE",
}

TEMP = "temperature"
C = "°C"
M = "measurement"

ITEMS: list[ItemDef] = [
    # --- states (binary) ---------------------------------------------------------------
    ItemDef(SOURCE_DATA, "IsHeatingPumpOn", "binary_sensor", "TČ běží", device_class="running", kind="bool", icon="mdi:heat-pump"),
    ItemDef(SOURCE_DATA, "IsResistorOn", "binary_sensor", "Spirála teplé vody", device_class="running", kind="bool", icon="mdi:heating-coil"),
    ItemDef(SOURCE_MENU, 337, "binary_sensor", "Záložní spirála topení", device_class="running", kind="bool", icon="mdi:heating-coil"),
    ItemDef(SOURCE_DATA, "IsDhwBoost", "binary_sensor", "Boost teplé vody", kind="bool", icon="mdi:water-boiler-alert"),
    ItemDef(SOURCE_DATA, "IsQuite", "binary_sensor", "Tichý režim", kind="bool", icon="mdi:volume-off"),
    ItemDef(SOURCE_DATA, "ZoneHeatRequest", "binary_sensor", "Požadavek na teplo", zone=1, kind="bool", icon="mdi:radiator"),
    ItemDef(SOURCE_DATA, "Holiday", "binary_sensor", "Dovolená", kind="bool", icon="mdi:palm-tree"),
    ItemDef(SOURCE_DATA, "AutomaticThermoregulation", "binary_sensor", "Ekvitermní regulace", kind="bool", icon="mdi:sun-thermometer", diagnostic=True),
    ItemDef(SOURCE_MENU, 304, "binary_sensor", "HV vstup 1", kind="bool", icon="mdi:electric-switch", diagnostic=True),
    # --- heat pump -----------------------------------------------------------------------
    ItemDef(SOURCE_MENU, 340, "sensor", "Režim TČ", kind="text", icon="mdi:heat-pump-outline", text_map=HP_MODE_TEXTS),
    ItemDef(SOURCE_MENU, 348, "sensor", "Teplota vody z TČ", device_class=TEMP, unit=C, state_class=M),
    ItemDef(SOURCE_MENU, 349, "sensor", "Teplota výstupu topení", device_class=TEMP, unit=C, state_class=M),
    ItemDef(SOURCE_DATA, "ChFlowSetpointTemp", "sensor", "Požadovaná teplota výstupu", device_class=TEMP, unit=C),
    ItemDef(SOURCE_DATA, "HeatingCircuitPressure", "sensor", "Tlak v systému", device_class="pressure", unit="bar", state_class=M),
    # --- outdoor -------------------------------------------------------------------------
    ItemDef(SOURCE_DATA, "OutsideTemp", "sensor", "Venkovní teplota", device_class=TEMP, unit=C, state_class=M),
    ItemDef(SOURCE_MENU, 341, "sensor", "Venkovní teplota (TČ)", device_class=TEMP, unit=C, state_class=M),
    ItemDef(SOURCE_MENU, 130, "sensor", "Venkovní teplota (online)", device_class=TEMP, unit=C, state_class=M, enabled=False),
    # --- room / zone 1 -------------------------------------------------------------------
    ItemDef(SOURCE_DATA, "ZoneMeasuredTemp", "sensor", "Teplota v místnosti", zone=1, device_class=TEMP, unit=C, state_class=M),
    ItemDef(SOURCE_MENU, 146, "sensor", "Vlhkost v místnosti", device_class="humidity", unit="%", state_class=M),
    ItemDef(SOURCE_DATA, "ZoneDesiredTemp", "sensor", "Požadovaná teplota místnosti", zone=1, device_class=TEMP, unit=C),
    ItemDef(SOURCE_DATA, "ZoneComfortTemp", "sensor", "Komfortní teplota místnosti", zone=1, device_class=TEMP, unit=C),
    ItemDef(SOURCE_DATA, "ZoneEconomyTemp", "sensor", "Útlumová teplota místnosti", zone=1, device_class=TEMP, unit=C),
    ItemDef(SOURCE_DATA, "ZoneMode", "sensor", "Režim zóny", zone=1, kind="text", icon="mdi:calendar-clock"),
    ItemDef(SOURCE_DATA, "HeatingFlowOffset", "sensor", "Posun topné křivky", zone=1, icon="mdi:chart-bell-curve", diagnostic=True),
    # --- domestic hot water --------------------------------------------------------------
    ItemDef(SOURCE_DATA, "DhwStorageTemperature", "sensor", "Teplota zásobníku TV", device_class=TEMP, unit=C, state_class=M),
    ItemDef(SOURCE_DATA, "DhwTemp", "sensor", "Požadovaná teplota TV", device_class=TEMP, unit=C),
    ItemDef(SOURCE_DATA, "DhwTimeProgComfortTemp", "sensor", "Komfortní teplota TV", device_class=TEMP, unit=C),
    ItemDef(SOURCE_DATA, "DhwTimeProgEconomyTemp", "sensor", "Útlumová teplota TV", device_class=TEMP, unit=C),
    ItemDef(SOURCE_DATA, "DhwMode", "sensor", "Režim TV", kind="text", icon="mdi:water-boiler"),
    # --- system / buffer -----------------------------------------------------------------
    ItemDef(SOURCE_DATA, "PlantMode", "sensor", "Režim systému", kind="text", icon="mdi:sun-snowflake-variant"),
    ItemDef(SOURCE_DATA, "BufferControlMode", "sensor", "Režim akumulace", kind="text", icon="mdi:storage-tank"),
    ItemDef(SOURCE_DATA, "BufferTimeProgComfortHeatingTemp", "sensor", "Komfortní teplota akumulace", device_class=TEMP, unit=C),
    ItemDef(SOURCE_DATA, "BufferTimeProgEconomyHeatingTemp", "sensor", "Útlumová teplota akumulace", device_class=TEMP, unit=C),
    # --- diagnostics ---------------------------------------------------------------------
    ItemDef(SOURCE_MENU, 303, "sensor", "HV vstup 1 – funkce", kind="text", icon="mdi:electric-switch", diagnostic=True, text_map=HV_INPUT_TEXTS),
    ItemDef(SOURCE_MENU, 119, "sensor", "Síla signálu", unit="%", state_class=M, icon="mdi:wifi", diagnostic=True),
]

# menuItems verified to work on a GALEVO / AEROTOP MONO.2 plant (probe 2026-10-13).
# Only these are requested - ONE unsupported number fails the whole request with HTTP 500.
# Known to crash the cloud (never request): 132, 306-335, 342-347, 310+ ranges outside the list.
MENU_IDS: list[int] = sorted({i.key for i in ITEMS if i.source == SOURCE_MENU})  # type: ignore[type-var]


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
