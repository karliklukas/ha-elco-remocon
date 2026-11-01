"""Sensors."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ITEMS, ItemDef
from .coordinator import RemoconConfigEntry, RemoconCoordinator, RemoconEnergyCoordinator
from .energy_values import BUCKET_ALIGNMENT, PERIOD_DAYS, PERIOD_MONTHS, TYPE_CH, TYPE_DHW, last_value
from .entity import RemoconEntity
from .values import sensor_value


async def async_setup_entry(
    hass: HomeAssistant, entry: RemoconConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [RemoconSensor(coordinator, item) for item in ITEMS if item.platform == "sensor"]
    if coordinator.energy is not None:
        entities += [RemoconEnergySensor(coordinator, *spec) for spec in ENERGY_SENSORS]
        entities.append(RemoconBucketEndSensor(coordinator))
    async_add_entities(entities)


# key (= unique id suffix and translation key), consumption type, period
ENERGY_SENSORS = [
    ("ch_yesterday", TYPE_CH, PERIOD_DAYS),
    ("dhw_yesterday", TYPE_DHW, PERIOD_DAYS),
    ("ch_last_month", TYPE_CH, PERIOD_MONTHS),
    ("dhw_last_month", TYPE_DHW, PERIOD_MONTHS),
]


class _EnergyEntity(CoordinatorEntity[RemoconEnergyCoordinator]):
    """Entity on the energy coordinator, attached to the same device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RemoconCoordinator, key: str) -> None:
        assert coordinator.energy is not None
        super().__init__(coordinator.energy)
        self._attr_unique_id = f"{coordinator.gateway}_energy_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.gateway)})


class RemoconEnergySensor(_EnergyEntity, SensorEntity):
    """Electricity consumed in a completed period (yesterday / previous month) - EM20 meter."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator: RemoconCoordinator, key: str, kind: int, period: int) -> None:
        super().__init__(coordinator, key)
        self._kind = kind
        self._period = period

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        return last_value(data.sequences, self._kind, self._period) if data else None


class RemoconBucketEndSensor(_EnergyEntity, SensorEntity):
    """End of the newest 2-hour consumption bucket - lets the user verify the time alignment (DST)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-end"

    def __init__(self, coordinator: RemoconCoordinator) -> None:
        super().__init__(coordinator, "bucket_end")

    @property
    def native_value(self):
        data = self.coordinator.data
        return data.bucket_end if data else None

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        return {"alignment": BUCKET_ALIGNMENT, "statistics_imported": data.imported if data else None}


class RemoconSensor(RemoconEntity, SensorEntity):
    """Numeric value, cloud-localized text or enum (state keys translated by Home Assistant)."""

    def __init__(self, coordinator: RemoconCoordinator, item: ItemDef) -> None:
        super().__init__(coordinator, item)
        if item.text_map:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = item.options
        elif item.device_class:
            self._attr_device_class = SensorDeviceClass(item.device_class)
        if item.state_class:
            self._attr_state_class = SensorStateClass(item.state_class)
        self._attr_native_unit_of_measurement = item.unit
        if item.kind == "number" and item.device_class:
            self._attr_suggested_display_precision = 1

    @property
    def native_value(self):
        return sensor_value(self.item, self.raw)
