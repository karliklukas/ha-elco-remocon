"""Sensors."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ITEMS, ItemDef
from .coordinator import RemoconConfigEntry, RemoconCoordinator
from .entity import RemoconEntity
from .values import sensor_value


async def async_setup_entry(
    hass: HomeAssistant, entry: RemoconConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(RemoconSensor(coordinator, item) for item in ITEMS if item.platform == "sensor")


class RemoconSensor(RemoconEntity, SensorEntity):
    """Numeric or text value."""

    def __init__(self, coordinator: RemoconCoordinator, item: ItemDef) -> None:
        super().__init__(coordinator, item)
        if item.device_class:
            self._attr_device_class = SensorDeviceClass(item.device_class)
        if item.state_class:
            self._attr_state_class = SensorStateClass(item.state_class)
        self._attr_native_unit_of_measurement = item.unit
        if item.kind == "number" and item.device_class:
            self._attr_suggested_display_precision = 1

    @property
    def native_value(self):
        return sensor_value(self.item, self.raw)
