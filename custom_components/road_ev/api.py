"""API client voor Road.io (E-flux)."""

from __future__ import annotations

import asyncio
import math
from typing import Any

import aiohttp

from .const import API_BASE_URL, API_TIMEOUT

_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Origin": "https://www.e-flux.io",
    "Referer": "https://www.e-flux.io/",
}

# Zo nauwkeurig groepeert de kaart-API zoekresultaten (zelfde als de webtool).
_GRID_PRECISION = 8
# Niet te veel locaties in één verzoek opvragen.
_LOCATIONS_BATCH = 50


class RoadApiError(Exception):
    """Algemene fout bij het praten met de Road.io API."""


class RoadConnectionError(RoadApiError):
    """De API was niet bereikbaar of gaf een ongeldig antwoord."""


class RoadLocationNotFoundError(RoadApiError):
    """De API kent het opgegeven Location ID niet."""


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Afstand in meters tussen twee punten (haversine)."""
    rad = math.radians
    a = (
        math.sin(rad(lat2 - lat1) / 2) ** 2
        + math.cos(rad(lat1))
        * math.cos(rad(lat2))
        * math.sin(rad(lon2 - lon1) / 2) ** 2
    )
    return 6371e3 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class RoadApiClient:
    """Minimale client voor de (onofficiële) kaart-API van Road.io."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialiseer de client met de gedeelde aiohttp sessie van HA."""
        self._session = session

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with asyncio.timeout(API_TIMEOUT):
                async with self._session.post(
                    f"{API_BASE_URL}{path}", json=payload, headers=_HEADERS
                ) as response:
                    response.raise_for_status()
                    result = await response.json(content_type=None)
        except TimeoutError as err:
            raise RoadConnectionError("Timeout bij verbinding met Road.io") from err
        except (aiohttp.ClientError, ValueError) as err:
            raise RoadConnectionError(f"API fout: {err}") from err

        if not isinstance(result, dict):
            raise RoadConnectionError("Onverwacht antwoord van de Road.io API")
        return result

    async def async_get_location(self, location_id: str) -> dict[str, Any]:
        """Haal één locatie op, inclusief operator, geoLocation en evses."""
        data = (await self._post("locations", {"ids": [location_id]})).get("data")
        if not data:
            raise RoadLocationNotFoundError(
                f"Geen locatie gevonden voor ID {location_id}"
            )
        return data[0]

    async def async_search(
        self, latitude: float, longitude: float, radius_m: float
    ) -> list[dict[str, Any]]:
        """Zoek laadlocaties binnen radius_m meter, dichtstbijzijnde eerst.

        Elke locatie krijgt een extra sleutel "distance" (meters tot het
        zoekpunt). Doet hetzelfde als de oude webtool, maar vanuit Home
        Assistant, dus zonder CORS-problemen en zonder reverse proxy.
        """
        dlat = radius_m / 111_320
        dlon = radius_m / (111_320 * max(math.cos(math.radians(latitude)), 0.01))
        bbox = {
            "nwLat": latitude + dlat,
            "nwLng": longitude - dlon,
            "seLat": latitude - dlat,
            "seLng": longitude + dlon,
        }
        found = (
            await self._post("search", {"gridPrecision": _GRID_PRECISION, "bbox": bbox})
        ).get("data") or []

        # Een zoekresultaat kan meerdere locaties bundelen: neem ze allemaal mee.
        ids: list[str] = []
        for item in found:
            if not isinstance(item, dict):
                continue
            for location_id in item.get("ids") or (
                [item["id"]] if "id" in item else []
            ):
                if location_id not in ids:
                    ids.append(location_id)

        locations: list[dict[str, Any]] = []
        for start in range(0, len(ids), _LOCATIONS_BATCH):
            batch = ids[start : start + _LOCATIONS_BATCH]
            result = await self._post("locations", {"ids": batch})
            locations.extend(
                loc for loc in result.get("data") or [] if isinstance(loc, dict)
            )

        results: list[dict[str, Any]] = []
        for location in locations:
            coords = (location.get("geoLocation") or {}).get("coordinates") or []
            if not location.get("id") or len(coords) != 2:
                continue
            try:
                dist = distance_m(
                    latitude, longitude, float(coords[1]), float(coords[0])
                )
            except (TypeError, ValueError):
                continue
            # De zoekbox is vierkant; houd alleen wat echt binnen de cirkel valt.
            if dist <= radius_m:
                results.append({**location, "distance": dist})

        results.sort(key=lambda loc: loc["distance"])
        return results
