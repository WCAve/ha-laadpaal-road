from datetime import timedelta
import logging
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

class EfluxDataUpdateCoordinator(DataUpdateCoordinator):
    """Beheert het ophalen van data."""

    def __init__(self, hass, api, location_id):
        self.api = api
        self.location_id = location_id
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        try:
            result = await self.api.async_get_locations(self.location_id)
            if not result or "data" not in result or not result["data"]:
                raise UpdateFailed("Geen data van Road.io")
            return result["data"][0].get("evses", [])
        except Exception as err:
            raise UpdateFailed(f"API Fout: {err}")