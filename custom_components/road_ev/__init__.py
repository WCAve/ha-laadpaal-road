"""Initialisatie van de EV Location Radar integratie."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .api import RoadApiClient
from .const import CARD_URL, CONF_LOCATION_ID, DOMAIN
from .coordinator import RoadDataUpdateCoordinator, location_gone_issue_id
from .price_watch import RoadPriceWatcher, storage_key
from .watcher import RoadWatcher

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class RoadData:
    """Alles wat bij één laadpaal (config entry) hoort."""

    coordinator: RoadDataUpdateCoordinator
    watcher: RoadWatcher


type RoadConfigEntry = ConfigEntry[RoadData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Registreer de Lovelace kaart (één keer per Home Assistant start)."""
    await _async_register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RoadConfigEntry) -> bool:
    """Zet de integratie op via de config entry."""
    _async_backfill_unique_id(hass, entry)

    api = RoadApiClient(async_get_clientsession(hass))
    coordinator = RoadDataUpdateCoordinator(hass, entry, api)

    # Haal direct de eerste dataset op; mislukt dit dan probeert HA het later opnieuw.
    await coordinator.async_config_entry_first_refresh()

    watcher = RoadWatcher(hass, entry, coordinator)
    watcher.async_start()
    await RoadPriceWatcher(hass, entry, coordinator, watcher).async_start()

    entry.runtime_data = RoadData(coordinator=coordinator, watcher=watcher)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RoadConfigEntry) -> bool:
    """Verwijder de integratie correct uit het geheugen."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: RoadConfigEntry) -> None:
    """Laadpaal verwijderd: ruim zijn reparatiemelding en bewaard tarief op."""
    ir.async_delete_issue(hass, DOMAIN, location_gone_issue_id(entry.entry_id))
    await Store(hass, 1, storage_key(entry.entry_id)).async_remove()


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serveer road-ev-card.js en laad hem in de frontend."""
    if hass.http is None:  # bv. tijdens tests zonder webserver
        return

    path = Path(__file__).parent / "frontend" / "road-ev-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(path), cache_headers=False)]
    )
    # Versie in de URL zodat browsers na een update de nieuwe kaart laden.
    integration = await async_get_integration(hass, DOMAIN)
    add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")


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
