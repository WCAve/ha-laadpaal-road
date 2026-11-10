"""Prijswijzigingen: meld het als het tarief van een laadpaal verandert.

Het laatst bekende tarief wordt per laadpaal bewaard (ook over herstarts),
zodat een wijziging terwijl Home Assistant uit stond ook gemeld wordt. We
vergelijken de leesbare samenvatting (prijs per kWh over de komende week,
starttarief, blokkeertarief), dus een dag/nacht-wissel of een nieuw
"lastUpdated" zonder echte prijswijziging levert geen melding op.

Naast de melding gaat er een event uit: ``road_ev_price_changed``, met
``entry_id``, ``name``, ``location_id``, ``before`` en ``after``.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import CONF_NOTIFY_PRICE_CHANGE, DOMAIN
from .tariff import describe, location_tariff

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import RoadDataUpdateCoordinator
    from .watcher import RoadWatcher

_LOGGER = logging.getLogger(__name__)

EVENT_PRICE_CHANGED = f"{DOMAIN}_price_changed"
STORAGE_VERSION = 1

_LABELS = {
    "prijs": "Prijs",
    "starttarief": "Starttarief",
    "blokkeertarief": "Blokkeertarief",
}


def storage_key(entry_id: str) -> str:
    """Opslagsleutel (in .storage/) voor één laadpaal."""
    return f"{DOMAIN}.{entry_id}.tarief"


def _canonical(tariff: dict[str, Any]) -> str:
    return json.dumps(tariff.get("elements"), sort_keys=True)


class RoadPriceWatcher:
    """Vergelijkt het tarief van één laadpaal met het vorige."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: RoadDataUpdateCoordinator,
        watcher: RoadWatcher,
    ) -> None:
        """Initialiseer (nog niet actief, zie async_start)."""
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.watcher = watcher
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, storage_key(entry.entry_id)
        )
        self._known: dict[str, Any] | None = None

    async def async_start(self) -> None:
        """Laad het bewaarde tarief en kijk meteen of het veranderd is."""
        stored = await self._store.async_load()
        if stored and isinstance(stored.get("tariff"), dict):
            self._known = stored["tariff"]
        self.entry.async_on_unload(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
        self._handle_coordinator_update()

    @callback
    def _handle_coordinator_update(self) -> None:
        if not self.coordinator.last_update_success:
            return
        data = self.coordinator.data
        tariff = location_tariff(data)
        if not tariff or not tariff.get("elements"):
            return  # geen (of half) tarief: niets concluderen
        current = {"elements": tariff["elements"]}

        if self._known is None:
            self._remember(current)  # eerste keer: alleen onthouden
            return
        if _canonical(current) == _canonical(self._known):
            return

        before = describe(data, self._known)
        after = describe(data, current)
        self._remember(current)
        changes = [
            f"{_LABELS[key]}: {before[key] or 'geen'} → {after[key] or 'geen'}"
            for key in _LABELS
            if before[key] != after[key]
        ]
        if not changes:
            _LOGGER.debug(
                "%s: tarief anders opgebouwd, prijzen gelijk", self.entry.title
            )
            return

        _LOGGER.info("%s: nieuw tarief: %s", self.entry.title, "; ".join(changes))
        self.hass.bus.async_fire(
            EVENT_PRICE_CHANGED,
            {
                "entry_id": self.entry.entry_id,
                "name": self.entry.title,
                "location_id": self.coordinator.location_id,
                "before": before,
                "after": after,
            },
        )
        if self.watcher.options.get(CONF_NOTIFY_PRICE_CHANGE):
            self.entry.async_create_background_task(
                self.hass,
                self.watcher.async_send(
                    f"💶 Nieuw tarief: {self.entry.title}",
                    "\n".join(changes),
                    stop_button=False,
                    tag_suffix="_tarief",
                ),
                f"{DOMAIN} price change notification",
            )

    @callback
    def _remember(self, tariff: dict[str, Any]) -> None:
        self._known = tariff
        self._store.async_delay_save(lambda: {"tariff": self._known}, 5)
