"""Schrijft de statistiek "vrij zonder mij" (zie own_sessions.py).

* Bij het opstarten (of na het kiezen van een sessie-entiteit): alles
  opnieuw uitrekenen vanaf het eerste uur waarvoor "Vrije sockets" statistiek
  bestaat, voor zover de geschiedenis van Home Assistant nog teruggaat.
* Daarna elk uur (kwart over): de afgelopen 24 uur opnieuw, omdat een
  sessie-entiteit het einde van een sessie soms pas uren later meldt.

Eenmaal geschreven blijft de statistiek bewaard, ook als de ruwe
geschiedenis allang is opgeruimd.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.recorder import get_instance, history
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    statistics_during_period,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import CONF_SESSION_ENTITY, DOMAIN
from .data import evses
from .own_sessions import corrected_mean, hourly_fractions, my_intervals

try:  # HA 2025.x+: mean_type vervangt has_mean
    from homeassistant.components.recorder.models import StatisticMeanType
except ImportError:  # pragma: no cover
    StatisticMeanType = None  # type: ignore[assignment,misc]

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import RoadDataUpdateCoordinator
    from .watcher import RoadWatcher

_LOGGER = logging.getLogger(__name__)

BACKFILL_MAX = timedelta(days=60)
RECENT_WINDOW = timedelta(hours=24)


def statistic_id(entry_id: str) -> str:
    """Id van de eigen statistiek voor één laadpaal."""
    return f"{DOMAIN}:vrij_zonder_mij_{entry_id.lower()}"


class RoadOwnSessionStats:
    """Houdt "vrij zonder mij" bij voor één laadpaal."""

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
        self.statistic_id = statistic_id(entry.entry_id)
        self.last_run: datetime | None = None
        self.last_hours_written = 0
        self.last_hours_corrected = 0

    @property
    def session_entity(self) -> str | None:
        """De gekozen sessie-entiteit, of None (dan doet dit niets)."""
        return self.watcher.options.get(CONF_SESSION_ENTITY) or None

    @callback
    def async_start(self) -> None:
        """Eén keer alles bijwerken, daarna elk uur."""
        if not self.session_entity:
            return
        self.entry.async_create_background_task(
            self.hass, self.async_update(full=True), f"{DOMAIN} own sessions backfill"
        )

        @callback
        def _hourly(_now: datetime) -> None:
            self.entry.async_create_background_task(
                self.hass, self.async_update(full=False), f"{DOMAIN} own sessions"
            )

        self.entry.async_on_unload(
            async_track_time_change(self.hass, _hourly, minute=15, second=0)
        )

    def _entity_id(self, unique_id: str) -> str | None:
        return er.async_get(self.hass).async_get_entity_id("sensor", DOMAIN, unique_id)

    async def async_update(self, full: bool) -> None:
        """Reken de uren in het venster uit en schrijf ze weg."""
        session_entity = self.session_entity
        location = self.coordinator.location_id
        free_entity = self._entity_id(f"road_{location}_free_sockets")
        if not session_entity or not free_entity:
            return

        sockets = evses(self.coordinator.data)
        socket_entities = {
            index: entity_id
            for index in range(len(sockets))
            if (entity_id := self._entity_id(f"road_{location}_status_{index}_final"))
        }

        now = dt_util.utcnow()
        last_complete = now.replace(minute=0, second=0, microsecond=0) - timedelta(
            hours=1
        )
        start = now - (BACKFILL_MAX if full else RECENT_WINDOW)
        start = start.replace(minute=0, second=0, microsecond=0)
        recorder = get_instance(self.hass)

        base = await recorder.async_add_executor_job(
            statistics_during_period,
            self.hass,
            start,
            last_complete + timedelta(hours=1),
            {free_entity},
            "hour",
            None,
            {"mean"},
        )
        rows = [r for r in base.get(free_entity, []) if r.get("mean") is not None]
        if not rows:
            return

        def _start(row: dict[str, Any]) -> datetime:
            value = row["start"]
            if isinstance(value, datetime):
                return value
            return dt_util.utc_from_timestamp(float(value))

        first_hour = _start(rows[0])
        states = await recorder.async_add_executor_job(
            lambda: history.get_significant_states(
                self.hass,
                first_hour - timedelta(hours=1),
                last_complete + timedelta(hours=1),
                [session_entity, *socket_entities.values()],
                None,
                True,  # include_start_time_state
                False,  # significant_changes_only: ook attribuut-wijzigingen
                False,  # minimal_response
                False,  # no_attributes
            )
        )
        intervals = my_intervals(
            states.get(session_entity, []),
            {i: states.get(e, []) for i, e in socket_entities.items()},
            sockets,
            last_complete + timedelta(hours=1),
        )
        fractions = hourly_fractions(intervals, (_start(r) for r in rows))
        total = len(sockets) or None

        data = [
            StatisticData(
                start=_start(r),
                mean=corrected_mean(
                    float(r["mean"]), fractions.get(_start(r), 0.0), total
                ),
            )
            for r in rows
        ]
        async_add_external_statistics(self.hass, self._metadata(), data)

        self.last_run = now
        self.last_hours_written = len(data)
        self.last_hours_corrected = len(fractions)
        _LOGGER.debug(
            "%s: vrij zonder mij bijgewerkt (%s uur, %s gecorrigeerd)",
            self.entry.title,
            len(data),
            len(fractions),
        )

    def _metadata(self) -> StatisticMetaData:
        meta: dict[str, Any] = {
            "has_mean": True,
            "has_sum": False,
            "name": f"{self.entry.title} vrij zonder mij",
            "source": DOMAIN,
            "statistic_id": self.statistic_id,
            "unit_of_measurement": None,
            "unit_class": None,
        }
        if StatisticMeanType is not None:
            meta["mean_type"] = StatisticMeanType.ARITHMETIC
        return meta  # type: ignore[return-value]

    def as_dict(self) -> dict[str, Any]:
        """Voor diagnostiek."""
        return {
            "session_entity": self.session_entity,
            "statistic_id": self.statistic_id,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "hours_written": self.last_hours_written,
            "hours_corrected": self.last_hours_corrected,
        }
