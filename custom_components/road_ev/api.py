"""API client voor Road.io (E-flux)."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import API_TIMEOUT, API_URL

_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Origin": "https://www.e-flux.io",
    "Referer": "https://www.e-flux.io/",
}


class RoadApiError(Exception):
    """Algemene fout bij het praten met de Road.io API."""


class RoadConnectionError(RoadApiError):
    """De API was niet bereikbaar of gaf een ongeldig antwoord."""


class RoadLocationNotFoundError(RoadApiError):
    """De API kent het opgegeven Location ID niet."""


class RoadApiClient:
    """Minimale client voor de (onofficiële) kaart-API van Road.io."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialiseer de client met de gedeelde aiohttp sessie van HA."""
        self._session = session

    async def async_get_location(self, location_id: str) -> dict[str, Any]:
        """Haal één locatie op, inclusief operator, geoLocation en evses."""
        try:
            async with asyncio.timeout(API_TIMEOUT):
                async with self._session.post(
                    API_URL, json={"ids": [location_id]}, headers=_HEADERS
                ) as response:
                    response.raise_for_status()
                    result = await response.json(content_type=None)
        except TimeoutError as err:
            raise RoadConnectionError("Timeout bij verbinding met Road.io") from err
        except (aiohttp.ClientError, ValueError) as err:
            raise RoadConnectionError(f"API fout: {err}") from err

        if not isinstance(result, dict):
            raise RoadConnectionError("Onverwacht antwoord van de Road.io API")

        data = result.get("data")
        if not data:
            raise RoadLocationNotFoundError(
                f"Geen locatie gevonden voor ID {location_id}"
            )
        return data[0]
