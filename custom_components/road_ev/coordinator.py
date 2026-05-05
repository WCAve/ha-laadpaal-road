"""DataUpdateCoordinator voor Road.io."""
import logging
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

class EfluxDataUpdateCoordinator(DataUpdateCoordinator):
    """Verwerkt de polling van de API elke 60 seconden."""

    def __init__(self, hass, api, location_id):
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{location_id}",
            update_interval=SCAN_INTERVAL,
        )
        self.api = api
        self.location_id = location_id

    async def _async_update_data(self):
        """Voer de daadwerkelijke update uit."""
        try:
            result = await self.api.async_get_locations(self.location_id)
            if not result or "data" not in result or not result["data"]:
                raise UpdateFailed("Ongeldige of geen data ontvangen van de API")
            
            # CRUCIALE FIX: Retourneer de volledige locatie-dictionary (index 0)
            # Hierin zitten: operator, geoLocation én de evses lijst.
            return result["data"][0]
            
        except Exception as err:
            raise UpdateFailed(f"Fout tijdens ophalen van data: {err}")