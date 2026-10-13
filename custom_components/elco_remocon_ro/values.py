"""Mapping of raw cloud items to entity states (no Home Assistant imports - unit-testable)."""

from __future__ import annotations

from typing import Any

from .api import item_text
from .const import SOURCE_DATA, ItemDef


def raw_for(item: ItemDef, data_items: dict[str, dict[str, Any]], menu_items: dict[int, dict[str, Any]]) -> dict[str, Any] | None:
    """Cloud item backing the entity, or None when the cloud did not deliver it."""
    if item.source == SOURCE_DATA:
        return data_items.get(f"{item.key}@{item.zone}")
    return menu_items.get(int(item.key))


def is_valid(raw: dict[str, Any] | None) -> bool:
    return raw is not None and not raw.get("error") and not raw.get("invalid") and raw.get("value") is not None


def sensor_value(item: ItemDef, raw: dict[str, Any] | None) -> Any:
    if not is_valid(raw):
        return None
    value = raw["value"]  # type: ignore[index]
    if item.kind == "text":
        if item.text_map:
            return item.text_map.get(int(value), f"Neznámý stav ({int(value)})")
        return item_text(raw) or str(value)  # type: ignore[arg-type]
    return value


def binary_value(raw: dict[str, Any] | None) -> bool | None:
    if not is_valid(raw):
        return None
    return float(raw["value"]) != 0  # type: ignore[index]
