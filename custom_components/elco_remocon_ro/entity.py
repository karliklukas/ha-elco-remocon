"""Base entity."""

from __future__ import annotations

from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, SOURCE_DATA, ItemDef
from .coordinator import RemoconCoordinator
from .values import is_valid, raw_for


class RemoconEntity(CoordinatorEntity[RemoconCoordinator]):
    """Entity backed by one cloud value."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RemoconCoordinator, item: ItemDef) -> None:
        super().__init__(coordinator)
        self.item = item
        gw = coordinator.gateway
        self._attr_unique_id = f"{gw}_{item.source}_{item.key}_{item.zone}"
        self._attr_name = item.name
        self._attr_icon = item.icon
        self._attr_entity_registry_enabled_default = item.enabled
        if item.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        plant = coordinator.plant
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gw)},
            name=coordinator.config_entry.title or "Tepelné čerpadlo",
            manufacturer=MANUFACTURER,
            model="Remocon-Net",
            sw_version=plant.get("gwFwVer"),
            serial_number=gw,
        )

    @property
    def raw(self) -> dict[str, Any] | None:
        """Current cloud item for this entity (None when not delivered)."""
        data = self.coordinator.data
        if data is None:
            return None
        return raw_for(self.item, data.data_items, data.menu_items)

    @property
    def available(self) -> bool:
        return super().available and is_valid(self.raw)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        raw = self.raw or {}
        attrs: dict[str, Any] = {"source": "dataItem" if self.item.source == SOURCE_DATA else "menuItem", "key": self.item.key}
        if raw.get("nodeId"):
            attrs["menu_node"] = raw["nodeId"]
        if self.item.kind == "text" and raw.get("value") is not None:
            attrs["raw_value"] = raw.get("value")
        return attrs
