"""Button: stuur een testmelding."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RoadConfigEntry
from .entity import RoadEntity
from .watcher import RoadWatcher

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RoadConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Maak de testmelding knop aan."""
    async_add_entities([RoadTestNotificationButton(entry.runtime_data.watcher)])


class RoadTestNotificationButton(RoadEntity, ButtonEntity):
    """Stuurt een melding zoals je die bij "vrij" krijgt."""

    _attr_name = "Testmelding"
    _attr_translation_key = "test_notification"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:bell-check-outline"

    def __init__(self, watcher: RoadWatcher) -> None:
        """Initialiseer de knop."""
        super().__init__(watcher.coordinator)
        self.watcher = watcher
        self._attr_unique_id = f"road_{self.location_id}_test_notification"

    @property
    def available(self) -> bool:
        """Ook testen als Road.io even plat ligt."""
        return True

    async def async_press(self) -> None:
        """Stuur de testmelding; fouten verschijnen in de UI."""
        _, message = self.watcher.free_message()
        await self.watcher.async_send(
            f"🔔 Testmelding: {self.watcher.name}",
            f"Zo ziet een melding eruit. Nu: {message}.",
            stop_button=False,
            raise_on_error=True,
            car=True,
        )
