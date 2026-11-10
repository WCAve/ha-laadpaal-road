"""Diagnostiek voor een laadpaal.

Downloaden: Instellingen > Apparaten & diensten > EV Location Radar > ⋮ > Diagnostiek.

Bevat de ruwe API-data van deze laadpaal (handig om tarieven of een
gewijzigde API te bekijken) en de toestand van de laadwens. Meldingsdoelen
en de gekozen persoon worden weggelaten.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from . import RoadConfigEntry
from .const import CONF_NOTIFY_TARGETS, CONF_PERSON, DOMAIN

TO_REDACT = {CONF_NOTIFY_TARGETS, CONF_PERSON}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: RoadConfigEntry
) -> dict[str, Any]:
    """Diagnostiek voor één laadpaal."""
    coordinator = entry.runtime_data.coordinator
    watcher = entry.runtime_data.watcher
    integration = await async_get_integration(hass, DOMAIN)

    def iso(value: Any) -> str | None:
        return value.isoformat() if value is not None else None

    return {
        "version": integration.version,
        "entry": {
            "title": entry.title,
            "data": dict(entry.data),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": repr(coordinator.last_exception)
            if coordinator.last_exception
            else None,
            "failing_since": iso(coordinator.failing_since),
        },
        "laadwens": {
            "armed": watcher.armed,
            "expires_at": iso(watcher.expires_at),
            "notified": watcher._notified,  # noqa: SLF001
            "follow_up_until": iso(watcher._follow_until),  # noqa: SLF001
        },
        "api_data": coordinator.data,
    }
