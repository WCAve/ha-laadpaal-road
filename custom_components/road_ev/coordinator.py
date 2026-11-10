"""DataUpdateCoordinator voor Road.io."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RoadApiClient, RoadApiError
from .const import CONF_LOCATION_ID, DOMAIN, SCAN_INTERVAL

if TYPE_CHECKING:
    from . import RoadConfigEntry

_LOGGER = logging.getLogger(__name__)


class RoadDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Haalt elke minuut de status van één laadlocatie op."""

    config_entry: RoadConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: RoadConfigEntry, api: RoadApiClient
    ) -> None:
        """Initialiseer de coordinator."""
        self.api = api
        self.location_id: str = entry.data[CONF_LOCATION_ID]
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{self.location_id}",
            update_interval=SCAN_INTERVAL,
            always_update=False,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Haal de volledige locatie-dictionary op (operator, geoLocation, evses)."""
        try:
            return await self.api.async_get_location(self.location_id)
        except RoadApiError as err:
            raise UpdateFailed(f"Fout tijdens ophalen van data: {err}") from err
