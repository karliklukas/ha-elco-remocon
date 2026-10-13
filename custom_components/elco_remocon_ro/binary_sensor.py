"""Binary sensors (on/off states)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ITEMS, ItemDef
from .coordinator import RemoconConfigEntry, RemoconCoordinator
from .entity import RemoconEntity
from .values import binary_value


async def async_setup_entry(
    hass: HomeAssistant, entry: RemoconConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(RemoconBinarySensor(coordinator, item) for item in ITEMS if item.platform == "binary_sensor")


class RemoconBinarySensor(RemoconEntity, BinarySensorEntity):
    """On/off state; any non-zero value is 'on'."""

    def __init__(self, coordinator: RemoconCoordinator, item: ItemDef) -> None:
        super().__init__(coordinator, item)
        if item.device_class:
            self._attr_device_class = BinarySensorDeviceClass(item.device_class)

    @property
    def is_on(self) -> bool | None:
        return binary_value(self.raw)
