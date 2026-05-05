import asyncio
import aiohttp
import logging

_LOGGER = logging.getLogger(__name__)

class EfluxApiClient:
    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
        self._base_url = "https://api.road.io/1/map"
        self._headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
            "Origin": "https://www.e-flux.io",
            "Referer": "https://www.e-flux.io/"
        }

    async def async_get_locations(self, location_id: str) -> dict:
        """Haal status op voor een specifieke locatie."""
        url = f"{self._base_url}/locations"
        payload = {"ids": [location_id]}
        
        try:
            async with asyncio.timeout(10):
                response = await self._session.post(
                    url, 
                    json=payload, 
                    headers=self._headers
                )
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            _LOGGER.error("Fout bij ophalen E-flux data: %s", e)
            raise