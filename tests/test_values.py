"""Mapping of cloud items to entity states (synthetic fixture, shaped like real responses)."""

from conftest import api, const, values

DATA_RESPONSE = {
    "items": [
        {"id": "IsHeatingPumpOn", "zone": 0, "kind": 3, "value": 1.0, "options": [0, 1], "optTexts": None, "readOnly": True, "error": False, "invalid": False},
        {"id": "IsResistorOn", "zone": 0, "kind": 3, "value": 0.0, "options": [0, 1], "optTexts": None, "readOnly": True, "error": False, "invalid": False},
        {"id": "PlantMode", "zone": 0, "kind": 2, "value": 1.0, "options": [0, 1, 2, 3], "optTexts": ["Léto", "Zima", "Pouze vytápění", "VYP."], "readOnly": False, "error": False, "invalid": False},
        {"id": "ZoneMeasuredTemp", "zone": 1, "kind": 1, "value": 20.3, "unit": "°C", "readOnly": True, "error": False, "invalid": False},
        {"id": "ZoneHeatRequest", "zone": 1, "kind": 2, "value": 1.0, "options": [0, 1], "optTexts": ["VYP.", "ON"], "readOnly": True, "error": False, "invalid": False},
        {"id": "DhwStorageTemperature", "zone": 0, "kind": 1, "value": 55.0, "unit": "°C", "error": False, "invalid": True},
    ]
}
MENU_RESPONSE = [
    {"id": 340, "nodeId": "T_13.9.0", "text": "Heat pump mode", "isEnum": True, "value": 9.0, "options": {"3": "Heating", "9": "Defrost"}, "error": False},
    {"id": 348, "nodeId": "T_13.8.1", "text": "HP water flow temp", "isEnum": False, "value": 33.0, "unit": "°C", "error": False},
    {"id": 337, "nodeId": "T_1.18.5", "text": "CH backup resistance 1", "isEnum": True, "value": 0.0, "options": {"0": "OFF", "1": "ON"}, "error": False},
    {"id": 303, "nodeId": "T_1.1.0", "text": "HV input 1", "isEnum": True, "value": 77.0, "options": {"0": "Not defined"}, "error": False},
]


def _item(key, zone=0):
    return next(i for i in const.ITEMS if i.key == key and i.zone == zone)


def _state(key, zone=0):
    di = api.index_data_items(DATA_RESPONSE)
    mi = api.index_menu_items(MENU_RESPONSE)
    item = _item(key, zone)
    raw = values.raw_for(item, di, mi)
    return values.binary_value(raw) if item.platform == "binary_sensor" else values.sensor_value(item, raw)


def test_binary_states():
    assert _state("IsHeatingPumpOn") is True
    assert _state("IsResistorOn") is False
    assert _state("ZoneHeatRequest", 1) is True  # enum 0/1 treated as on/off
    assert _state(337) is False


def test_enum_texts():
    assert _state("PlantMode") == "Zima"  # localized optTexts from the cloud
    assert _state(340) == "Odmrazování"  # menu enum mapped to Czech
    assert _state(303) == "Neznámý stav (77)"  # value outside the map does not crash


def test_numbers_and_missing():
    assert _state("ZoneMeasuredTemp", 1) == 20.3
    assert _state(348) == 33.0
    assert _state("DhwStorageTemperature") is None  # flagged invalid by the cloud
    assert _state(349) is None  # not delivered


def test_menu_ids_are_only_verified_numbers():
    crashing = {132, *range(306, 336), *range(342, 348)}
    assert set(const.MENU_IDS) == {119, 130, 146, 303, 304, 337, 340, 341, 348, 349}
    assert not set(const.MENU_IDS) & crashing


def test_data_item_request_per_zone():
    req = const.data_item_request([1, 2])
    assert {"id": "ZoneMeasuredTemp", "zn": 1} in req and {"id": "ZoneMeasuredTemp", "zn": 2} in req
    assert {"id": "IsHeatingPumpOn", "zn": 0} in req
    assert len(req) == len({(r["id"], r["zn"]) for r in req})


def test_unique_ids_unique():
    keys = [(i.source, i.key, i.zone) for i in const.ITEMS]
    assert len(keys) == len(set(keys))
