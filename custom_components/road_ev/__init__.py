"""Initialisatie van de Road.io (E-flux) integratie."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RoadApiClient
from .const import CONF_LOCATION_ID, DOMAIN
from .coordinator import RoadDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type RoadConfigEntry = ConfigEntry[RoadDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: RoadConfigEntry) -> bool:
    """Zet de integratie op via de config entry."""
    _async_backfill_unique_id(hass, entry)

    api = RoadApiClient(async_get_clientsession(hass))
    coordinator = RoadDataUpdateCoordinator(hass, entry, api)

    # Haal direct de eerste dataset op; mislukt dit dan probeert HA het later opnieuw.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RoadConfigEntry) -> bool:
    """Verwijder de integratie correct uit het geheugen."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _async_backfill_unique_id(hass: HomeAssistant, entry: RoadConfigEntry) -> None:
    """Geef entries van vóór v2.2 alsnog het Location ID als unique_id.

    Daarmee weigert de config flow voortaan dubbele locaties. Als dezelfde
    locatie al twee keer is toegevoegd, laten we de tweede ongemoeid.
    """
    if entry.unique_id is not None:
        return
    location_id = entry.data[CONF_LOCATION_ID]
    if any(
        other.unique_id == location_id
        for other in hass.config_entries.async_entries(DOMAIN)
    ):
        return
    hass.config_entries.async_update_entry(entry, unique_id=location_id)
