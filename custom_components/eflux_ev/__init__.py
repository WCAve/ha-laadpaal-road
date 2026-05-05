import logging
from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .api import EfluxApiClient
from .const import DOMAIN
from .coordinator import EfluxDataUpdateCoordinator

PLATFORMS = [Platform.SENSOR]

async def async_setup_entry(hass, entry):
    session = async_get_clientsession(hass)
    api = EfluxApiClient(session)
    coordinator = EfluxDataUpdateCoordinator(hass, api, entry.data["location_id"])

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)