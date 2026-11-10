"""Switch: "Laadwens" (ik wil hier laden, meld als er plek is)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from . import RoadConfigEntry
from .entity import RoadEntity
from .watcher import RoadWatcher

PARALLEL_UPDATES = 0

ATTR_EXPIRES_AT = "verloopt_om"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RoadConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Maak de Laadwens switch aan."""
    async_add_entities([RoadChargeWishSwitch(entry.runtime_data.watcher)])


class RoadChargeWishSwitch(RoadEntity, SwitchEntity, RestoreEntity):
    """Zet de laadwens aan of uit. De logica zit in RoadWatcher."""

    _attr_name = "Laadwens"
    _attr_translation_key = "charge_wish"

    def __init__(self, watcher: RoadWatcher) -> None:
        """Initialiseer de switch."""
        super().__init__(watcher.coordinator)
        self.watcher = watcher
        self._attr_unique_id = f"road_{self.location_id}_charge_wish"

    async def async_added_to_hass(self) -> None:
        """Herstel de laadwens van vóór een herstart en volg de watcher."""
        await super().async_added_to_hass()
        self.async_on_remove(self.watcher.async_add_listener(self.async_write_ha_state))

        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state == STATE_ON:
            expires = last_state.attributes.get(ATTR_EXPIRES_AT)
            self.watcher.async_restore(
                dt_util.parse_datetime(expires) if expires else None
            )

    @property
    def available(self) -> bool:
        """De laadwens is altijd te bedienen, ook als de API even plat ligt."""
        return True

    @property
    def is_on(self) -> bool:
        """Staat de laadwens aan?"""
        return self.watcher.armed

    @property
    def icon(self) -> str:
        """Bel aan of uit."""
        return "mdi:bell-ring" if self.is_on else "mdi:bell-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Wanneer de laadwens vanzelf uitgaat (voor de kaart en herstarts)."""
        expires = self.watcher.expires_at
        return {ATTR_EXPIRES_AT: expires.isoformat() if expires else None}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Laadwens aan."""
        self.watcher.async_arm()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Laadwens uit (ook geen "weer bezet" melding meer)."""
        self.watcher.async_disarm(stop_follow_up=True)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Nieuwe data verandert niets aan de switch zelf."""
