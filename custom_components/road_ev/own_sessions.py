"""Eigen laadsessies uit de "meestal vrij"-statistiek halen.

Een sessie-entiteit uit een andere integratie (bv. de Tap Electric
"Charging status" sensor) vertelt via het attribuut ``outlet_name`` op welke
socket je laadt, bijvoorbeeld ``ALF-0075798-1``. Dat is dezelfde code als
het socket-ID uit de API (``NL*NUO*EALF*0075798*1``), anders geschreven.

Begin en eind komen niet van die sessie-entiteit (die werkt soms pas uren
later bij), maar van de status van onze eigen socket-sensor, die elke minuut
ververst: een periode waarin jouw socket bezet was en die overlapt met een
sessie van jou op die socket, telt helemaal als "van jou".

Per uur: vrij zonder mij = gemiddeld vrij + (deel van het uur dat jij er
stond), afgetopt op het aantal sockets. Dat komt in een eigen statistiek
(``road_ev:vrij_zonder_mij_<id>``); de statistiek van Home Assistant zelf
blijft onaangeroerd.
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

# Statussen van onze socket-sensor die "bezet" betekenen.
BUSY_STATES = {"Bezet", "Geblokkeerd"}
# Sessie-entiteit: deze waarden betekenen "geen sessie".
INACTIVE_SESSION_STATES = {
    "",
    "idle",
    "not charging",
    "unavailable",
    "unknown",
    "none",
    "off",
}
_MIN_CODE_LENGTH = 6


class StateLike(Protocol):
    """Wat we van een recorder-State gebruiken."""

    state: str
    attributes: dict[str, Any]
    last_updated: datetime
    last_changed: datetime


@dataclass(frozen=True)
class Interval:
    """Tijdvak [start, end)."""

    start: datetime
    end: datetime

    def overlaps(self, other: Interval) -> bool:
        return self.start < other.end and other.start < self.end

    def overlap_seconds(self, start: datetime, end: datetime) -> float:
        latest = max(self.start, start)
        earliest = min(self.end, end)
        return max((earliest - latest).total_seconds(), 0.0)


def normalize_code(value: Any) -> str:
    """'NL*NUO*EALF*0075798*1' -> 'NLNUOEALF00757981'."""
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def socket_codes(evse: dict[str, Any]) -> set[str]:
    """Alle codes waaronder een socket bekend kan zijn."""
    return {
        code
        for code in (
            normalize_code(evse.get(key))
            for key in ("evseId", "evse_id", "uid", "physicalReference")
        )
        if code
    }


def match_socket(outlet: Any, evses: Sequence[dict[str, Any]]) -> int | None:
    """Index van de socket die bij een outlet-code hoort, of None.

    Matcht als de genormaliseerde outlet-code gelijk is aan, of het einde is
    van, een code van de socket ("ALF00757981" in "NLNUOEALF00757981").
    """
    code = normalize_code(outlet)
    if len(code) < _MIN_CODE_LENGTH:
        return None
    for index, evse in enumerate(evses):
        if any(c == code or c.endswith(code) for c in socket_codes(evse)):
            return index
    return None


def session_intervals(
    rows: Iterable[StateLike], end: datetime
) -> list[tuple[Interval, str]]:
    """(tijdvak, outlet) waarin de sessie-entiteit een actieve sessie meldde."""
    result: list[tuple[Interval, str]] = []
    rows = sorted(rows, key=lambda r: r.last_updated)
    for i, row in enumerate(rows):
        outlet = (row.attributes or {}).get("outlet_name")
        if not outlet or str(row.state).strip().lower() in INACTIVE_SESSION_STATES:
            continue
        stop = rows[i + 1].last_updated if i + 1 < len(rows) else end
        if stop > row.last_updated:
            result.append((Interval(row.last_updated, stop), str(outlet)))
    return result


def busy_intervals(rows: Iterable[StateLike], end: datetime) -> list[Interval]:
    """Aaneengesloten tijdvakken waarin een socket bezet was."""
    result: list[Interval] = []
    rows = sorted(rows, key=lambda r: r.last_changed)
    start: datetime | None = None
    for row in rows:
        busy = row.state in BUSY_STATES
        if busy and start is None:
            start = row.last_changed
        elif not busy and start is not None:
            result.append(Interval(start, row.last_changed))
            start = None
    if start is not None and end > start:
        result.append(Interval(start, end))
    return result


def my_intervals(
    session_rows: Iterable[StateLike],
    socket_rows: dict[int, Iterable[StateLike]],
    evses: Sequence[dict[str, Any]],
    end: datetime,
) -> list[Interval]:
    """Bezet-periodes van jouw socket die overlappen met jouw sessies."""
    sessions_per_socket: dict[int, list[Interval]] = {}
    for interval, outlet in session_intervals(session_rows, end):
        index = match_socket(outlet, evses)
        if index is not None:
            sessions_per_socket.setdefault(index, []).append(interval)

    mine: list[Interval] = []
    for index, sessions in sessions_per_socket.items():
        for busy in busy_intervals(socket_rows.get(index, []), end):
            if any(busy.overlaps(session) for session in sessions):
                mine.append(busy)
    return mine


def hourly_fractions(
    intervals: Sequence[Interval], hours: Iterable[datetime]
) -> dict[datetime, float]:
    """Per uur (start) het deel van het uur dat jij een socket bezette.

    Twee sockets tegelijk (komt in de praktijk niet voor) telt dubbel.
    """
    result: dict[datetime, float] = {}
    for hour in hours:
        end = hour + timedelta(hours=1)
        seconds = sum(i.overlap_seconds(hour, end) for i in intervals)
        if seconds:
            result[hour] = seconds / 3600
    return result


def corrected_mean(base_mean: float, mine: float, total: int | None) -> float:
    """Gemiddeld vrij zonder jou, nooit meer dan het aantal sockets."""
    value = base_mean + mine
    if total:
        value = min(value, float(total))
    return round(value, 4)


UNKNOWN_STATES = {"unavailable", "unknown", ""}
_MIN_KNOWN_MINUTES = 30


def free_chance(
    socket_rows: dict[int, Sequence[StateLike]],
    mine: Sequence[Interval],
    hours: Iterable[datetime],
) -> dict[datetime, float]:
    """Per uur het deel van de tijd dat er minstens één socket vrij was.

    Bemonsterd per minuut. Een socket die jij bezette telt als vrij (zonder
    jou was hij dat geweest). Minuten waarin een socket een onbekende status
    had (bv. API plat) tellen niet mee; met minder dan 30 bekende minuten
    krijgt het uur geen waarde.
    """
    timelines: list[tuple[list[datetime], list[str]]] = []
    for rows in socket_rows.values():
        ordered = sorted(rows, key=lambda r: r.last_changed)
        timelines.append(
            ([r.last_changed for r in ordered], [r.state for r in ordered])
        )
    if not timelines:
        return {}

    result: dict[datetime, float] = {}
    for hour in hours:
        known = free = 0
        for minute in range(60):
            moment = hour + timedelta(minutes=minute, seconds=30)
            mine_now = any(i.start <= moment < i.end for i in mine)
            states: list[str] = []
            for times, values in timelines:
                pos = bisect.bisect_right(times, moment) - 1
                states.append(values[pos] if pos >= 0 else "")
            if any(state in UNKNOWN_STATES for state in states):
                continue
            known += 1
            if mine_now or any(state not in BUSY_STATES for state in states):
                free += 1
        if known >= _MIN_KNOWN_MINUTES:
            result[hour] = round(free / known, 4)
    return result
