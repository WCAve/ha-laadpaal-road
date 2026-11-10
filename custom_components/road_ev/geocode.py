"""Adres opzoeken via OpenStreetMap Nominatim (alleen bij het toevoegen).

Gebruiksregels van Nominatim waar we ons aan houden:
https://operations.osmfoundation.org/policies/nominatim/

* Eén verzoek per keer dat de gebruiker op Verzenden drukt, nooit tijdens
  het typen en nooit op een timer.
* Een User-Agent die deze integratie noemt.
* Dezelfde zoekterm wordt binnen een flow niet nog eens opgevraagd.
* Bronvermelding (© OpenStreetMap) staat in het formulier.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import aiohttp

from .const import GEOCODE_TIMEOUT, GEOCODE_URL, GEOCODE_USER_AGENT


class GeocodeError(Exception):
    """Nominatim was niet bereikbaar of gaf een ongeldig antwoord."""


@dataclass(frozen=True)
class Place:
    """Een gevonden plek."""

    latitude: float
    longitude: float
    name: str


async def async_geocode(
    session: aiohttp.ClientSession, query: str, language: str = "nl"
) -> Place | None:
    """Zoek één adres of plaatsnaam op. None als er niets gevonden is."""
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": "1",
        "addressdetails": "0",
        "accept-language": language,
    }
    headers = {"User-Agent": GEOCODE_USER_AGENT}
    try:
        async with asyncio.timeout(GEOCODE_TIMEOUT):
            async with session.get(
                GEOCODE_URL, params=params, headers=headers
            ) as response:
                response.raise_for_status()
                results = await response.json(content_type=None)
    except TimeoutError as err:
        raise GeocodeError("Timeout bij OpenStreetMap") from err
    except (aiohttp.ClientError, ValueError) as err:
        raise GeocodeError(f"OpenStreetMap fout: {err}") from err

    if not isinstance(results, list):
        raise GeocodeError("Onverwacht antwoord van OpenStreetMap")
    if not results:
        return None
    first = results[0]
    try:
        return Place(
            latitude=float(first["lat"]),
            longitude=float(first["lon"]),
            name=str(first.get("display_name") or query),
        )
    except (KeyError, TypeError, ValueError) as err:
        raise GeocodeError("Onverwacht antwoord van OpenStreetMap") from err
