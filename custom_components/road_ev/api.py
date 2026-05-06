"""API Client voor Road.io (E-flux)."""
import asyncio
import logging
import aiohttp

_LOGGER = logging.getLogger(__name__)

class EfluxApiClient:
    """Basis API client."""
    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
        self._headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Origin": "https://www.e-flux.io",
            "Referer": "https://www.e-flux.io/"
        }

    async def async_get_locations(self, location_id: str) -> dict:
        """Haal laadpaal data op via POST request."""
        url = "https://api.road.io/1/map/locations"
        payload = {"ids": [location_id]}
        
        try:
            async with asyncio.timeout(10):
                async with self._session.post(url, json=payload, headers=self._headers) as response:
                    response.raise_for_status()
                    return await response.json(content_type=None)
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout bij verbinding met Road.io")
            raise
        except (aiohttp.ClientError, ValueError) as e:
            _LOGGER.error("API fout: %s", e)
            raise