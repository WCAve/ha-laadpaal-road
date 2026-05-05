"""Initialisatie van de Road.io (E-flux) integratie."""
import logging
from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .api import EfluxApiClient
from .const import DOMAIN
from .coordinator import EfluxDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]

async def async_setup_entry(hass, entry):
    """Zet de integratie op via de config entry."""
    session = async_get_clientsession(hass)
    api = EfluxApiClient(session)
    location_id = entry.data["location_id"]
    
    coordinator = EfluxDataUpdateCoordinator(hass, api, location_id)

    # Haal direct de eerste dataset op
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass, entry):
    """Verwijder de integratie correct uit het geheugen."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok