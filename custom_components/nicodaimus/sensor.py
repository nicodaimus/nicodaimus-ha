"""Sensor platform for nicodAImus account status."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NicodaimusConfigEntry
from .const import DOMAIN
from .coordinator import NicodaimusAccountData, NicodaimusStatusCoordinator


@dataclass(frozen=True, kw_only=True)
class NicodaimusSensorEntityDescription(SensorEntityDescription):
    """Describes a nicodAImus sensor entity."""

    value_fn: Callable[[NicodaimusAccountData], str | int | float | None]


SENSOR_DESCRIPTIONS: tuple[NicodaimusSensorEntityDescription, ...] = (
    NicodaimusSensorEntityDescription(
        key="tier",
        translation_key="tier",
        icon="mdi:shield-account",
        value_fn=lambda data: data.tier_name,
    ),
    NicodaimusSensorEntityDescription(
        key="subscription_status",
        translation_key="subscription_status",
        icon="mdi:card-account-details",
        value_fn=lambda data: data.subscription_status,
    ),
    NicodaimusSensorEntityDescription(
        key="searches_today",
        translation_key="searches_today",
        icon="mdi:magnify",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.search_day_count,
    ),
    NicodaimusSensorEntityDescription(
        key="searches_month",
        translation_key="searches_month",
        icon="mdi:magnify",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.search_month_count,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NicodaimusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up nicodAImus sensor entities."""
    coordinator = entry.runtime_data.coordinator

    async_add_entities(
        NicodaimusSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class NicodaimusSensor(CoordinatorEntity[NicodaimusStatusCoordinator], SensorEntity):
    """A nicodAImus account sensor."""

    entity_description: NicodaimusSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NicodaimusStatusCoordinator,
        entry: NicodaimusConfigEntry,
        description: NicodaimusSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="nicodAImus Account",
            manufacturer="nicodAImus",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> str | int | float | None:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
