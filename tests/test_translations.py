"""Every entity has a name (and every enum state a text) in strings.json and all translations."""

import ast
import json
from pathlib import Path

import pytest

from conftest import const

DIR = Path(__file__).resolve().parents[1] / "custom_components" / "elco_remocon_ro"
FILES = [DIR / "strings.json", *sorted((DIR / "translations").glob("*.json"))]


def _energy_keys() -> list[str]:
    """Translation keys of the energy sensors (sensor.py imports Home Assistant - read it with ast)."""
    tree = ast.parse((DIR / "sensor.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "ENERGY_SENSORS" for t in node.targets):
            return [elt.elts[0].value for elt in node.value.elts] + ["bucket_end"]
    raise AssertionError("ENERGY_SENSORS not found")


def _expected() -> dict[str, dict[str, list[str]]]:
    """platform -> translation key -> enum states."""
    out: dict[str, dict[str, list[str]]] = {"binary_sensor": {}, "sensor": {}}
    for item in const.ITEMS:
        out[item.platform][item.translation_key] = item.options
    for key in _energy_keys():
        out["sensor"][key] = []
    return out


def test_translation_keys_unique():
    keys = [(i.platform, i.translation_key) for i in const.ITEMS]
    assert len(keys) == len(set(keys))


def test_languages_present():
    assert {f.name for f in FILES} == {"strings.json", "cs.json", "de.json", "en.json"}


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_entities_translated(path):
    entity = json.loads(path.read_text(encoding="utf-8"))["entity"]
    expected = _expected()
    for platform, keys in expected.items():
        assert set(entity[platform]) == set(keys), f"{path.name}: {platform} keys differ"
        for key, states in keys.items():
            assert entity[platform][key]["name"].strip(), f"{path.name}: {platform}.{key} has no name"
            assert set(entity[platform][key].get("state", {})) == set(states), f"{path.name}: {platform}.{key} states differ"


@pytest.mark.parametrize("path", FILES[1:], ids=lambda p: p.name)
def test_same_structure_as_strings(path):
    def keys(obj, prefix=""):
        if isinstance(obj, dict):
            return {k for name, value in obj.items() for k in keys(value, f"{prefix}{name}.")}
        return {prefix}

    strings = json.loads(FILES[0].read_text(encoding="utf-8"))
    assert keys(json.loads(path.read_text(encoding="utf-8"))) == keys(strings)
