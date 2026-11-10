"""Binary sensor: is er minstens één socket vrij?"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RoadConfigEntry
from .coordinator import RoadDataUpdateCoordinator
from .data import free_count
from .entity import RoadEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RoadConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Maak de "Vrij" sensor aan."""
    async_add_entities([RoadFreeBinarySensor(entry.runtime_data.coordinator)])


class RoadFreeBinarySensor(RoadEntity, BinarySensorEntity):
    """Aan zodra er minstens één socket vrij is."""

    _attr_name = "Vrij"
    _attr_translation_key = "free"

    def __init__(self, coordinator: RoadDataUpdateCoordinator) -> None:
        """Initialiseer de sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"road_{self.location_id}_free"

    @property
    def is_on(self) -> bool:
        """Minstens één socket heeft status AVAILABLE."""
        return free_count(self.coordinator.data) > 0

    @property
    def icon(self) -> str:
        """Ander icoon voor vrij en bezet."""
        return "mdi:ev-station" if self.is_on else "mdi:ev-plug-type2"
