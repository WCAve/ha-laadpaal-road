"""DataUpdateCoordinator: haalt de laadpaaldata op."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    RoadApiClient,
    RoadApiError,
    RoadFormatError,
    RoadLocationNotFoundError,
)
from .const import CONF_LOCATION_ID, DOMAIN, SCAN_INTERVAL, UNREACHABLE_REPAIR_AFTER

if TYPE_CHECKING:
    from . import RoadConfigEntry

_LOGGER = logging.getLogger(__name__)

# Reparatiemeldingen (Instellingen > Systeem > Reparaties)
ISSUE_UNREACHABLE = "api_unreachable"
ISSUE_API_CHANGED = "api_changed"
ISSUE_LOCATION_GONE = "location_gone"


def location_gone_issue_id(entry_id: str) -> str:
    """Issue-id voor "deze laadpaal bestaat niet meer" (per laadpaal)."""
    return f"{ISSUE_LOCATION_GONE}_{entry_id}"


class RoadDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Haalt elke minuut de status van één laadlocatie op."""

    config_entry: RoadConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: RoadConfigEntry, api: RoadApiClient
    ) -> None:
        """Initialiseer de coordinator."""
        self.api = api
        self.location_id: str = entry.data[CONF_LOCATION_ID]
        self.failing_since: datetime | None = None
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{self.location_id}",
            update_interval=SCAN_INTERVAL,
            always_update=False,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Haal de volledige locatie-dictionary op (operator, geoLocation, evses)."""
        gone_issue = location_gone_issue_id(self.config_entry.entry_id)
        try:
            data = await self.api.async_get_location(self.location_id)
        except RoadLocationNotFoundError as err:
            self._create_issue(
                gone_issue,
                ISSUE_LOCATION_GONE,
                ir.IssueSeverity.ERROR,
                {"name": self.config_entry.title, "location_id": self.location_id},
            )
            raise UpdateFailed(str(err)) from err
        except RoadFormatError as err:
            self._create_issue(
                ISSUE_API_CHANGED,
                ISSUE_API_CHANGED,
                ir.IssueSeverity.ERROR,
                {"error": str(err)},
            )
            raise UpdateFailed(f"Onverwacht antwoord van de API: {err}") from err
        except RoadApiError as err:
            now = dt_util.utcnow()
            if self.failing_since is None:
                self.failing_since = now
            elif now - self.failing_since >= UNREACHABLE_REPAIR_AFTER:
                self._create_issue(
                    ISSUE_UNREACHABLE,
                    ISSUE_UNREACHABLE,
                    ir.IssueSeverity.WARNING,
                    {"since": dt_util.as_local(self.failing_since).strftime("%H:%M")},
                )
            raise UpdateFailed(f"Fout tijdens ophalen van data: {err}") from err

        # Alles weer in orde: eventuele reparatiemeldingen opruimen.
        self.failing_since = None
        for issue_id in (ISSUE_UNREACHABLE, ISSUE_API_CHANGED, gone_issue):
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        return data

    def _create_issue(
        self,
        issue_id: str,
        translation_key: str,
        severity: ir.IssueSeverity,
        placeholders: dict[str, str],
    ) -> None:
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=severity,
            translation_key=translation_key,
            translation_placeholders=placeholders,
            learn_more_url="https://github.com/WCAve/ha-laadpaal-road",
        )
