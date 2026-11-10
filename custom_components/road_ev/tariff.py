"""Tarieven van Road.io uitlezen (OCPI-achtig formaat).

Een tarief bestaat uit "elements", elk met "priceComponents" en optionele
"restrictions". Per soort component (ENERGY, FLAT, TIME, PARKING_TIME) geldt
het eerste element waarvan de voorwaarden kloppen. Prijzen zijn exclusief btw;
ENERGY is per kWh, FLAT per sessie, TIME en PARKING_TIME per uur.

Voorwaarden die we meenemen: tijd van de dag (ook over middernacht heen),
weekdag, datum, sessieduur en geladen kWh. Vermogen en stroom kunnen we niet
weten en tellen als "klopt".

Getest met echte tarieven van Plugfuse (kWh + starttarief), Vattenfall
(kWh vanaf een startdatum), Allego (kWh, na 5 uur €3/u tussen 07 en 23 uur)
en Qwello (kWh + €0,30/u vanaf de start, tijdens en na het laden).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ENERGY = "ENERGY"
FLAT = "FLAT"
TIME = "TIME"
PARKING_TIME = "PARKING_TIME"

_WEEKDAYS = [
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
]
_DEFAULT_TZ = "Europe/Amsterdam"


@dataclass(frozen=True)
class BlockingFee:
    """Prijs per uur die na een gratis periode gaat tellen."""

    per_hour: float  # incl. btw, hoogste van laden/stilstaan
    charging_per_hour: float  # TIME, incl. btw
    parking_per_hour: float  # PARKING_TIME, incl. btw
    free_minutes: int  # zo lang gratis vanaf de start van je sessie
    until_minutes: int | None  # daarna weer gratis (None = geen einde)
    window: str | None  # bv. "07:00–23:00", None = de hele dag
    days: tuple[str, ...] | None  # bv. ("MONDAY", ...), None = elke dag

    @property
    def text(self) -> str:
        """Korte omschrijving, bv. "na 5 u €3,00/u (07:00–23:00)".

        Telt het vanaf de eerste minuut: "€0,30/u vanaf de start".
        """
        price = _euro(self.per_hour) + "/u"
        if self.free_minutes:
            text = f"na {_duration(self.free_minutes)} {price}"
        else:
            text = f"{price} vanaf de start"
        extras = []
        if self.window:
            extras.append(self.window)
        if self.days:
            extras.append(", ".join(day[:2].lower() for day in self.days))
        return f"{text} ({'; '.join(extras)})" if extras else text


@dataclass(frozen=True)
class TariffNow:
    """Wat er nu geldt voor een nieuwe sessie."""

    energy: float | None  # per kWh incl. btw
    start_fee: float  # per sessie incl. btw (0 = geen)
    blocking_fee: BlockingFee | None


def incl_vat(component: dict[str, Any]) -> float:
    """Prijs incl. btw van één price component."""
    price = float(component.get("price") or 0)
    vat = float(component.get("vat") or 0)
    return price * (1 + vat / 100)


def location_tariff(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Tarief van de eerste connector van de eerste socket."""
    try:
        tariff = data["evses"][0]["connectors"][0]["tariff"]  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        return None
    return tariff if isinstance(tariff, dict) else None


def tariffs_differ(data: dict[str, Any] | None) -> bool:
    """Hebben de sockets van deze locatie verschillende tarieven?"""
    ids = set()
    for evse in (data or {}).get("evses") or []:
        for connector in evse.get("connectors") or []:
            tariff = connector.get("tariff") or {}
            ids.add(tariff.get("id") or repr(tariff.get("elements")))
    return len(ids) > 1


def local_now(data: dict[str, Any] | None, now: datetime | None = None) -> datetime:
    """Huidige tijd in de tijdzone van de laadlocatie."""
    tz_name = (data or {}).get("timezone") or _DEFAULT_TZ
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo(_DEFAULT_TZ)
    return (now or datetime.now(UTC)).astimezone(tz)


def components_at(
    tariff: dict[str, Any] | None,
    when: datetime,
    duration_s: float = 0,
    kwh: float = 0,
) -> dict[str, dict[str, Any]]:
    """Per soort het geldende price component op moment `when` (lokale tijd)."""
    result: dict[str, dict[str, Any]] = {}
    for element in (tariff or {}).get("elements") or []:
        if not isinstance(element, dict):
            continue
        if not _matches(element.get("restrictions") or {}, when, duration_s, kwh):
            continue
        for component in element.get("priceComponents") or []:
            kind = component.get("type") if isinstance(component, dict) else None
            if kind and kind not in result:
                result[kind] = component
    return result


def evaluate(data: dict[str, Any] | None, now: datetime | None = None) -> TariffNow:
    """Tarief voor een sessie die nu start, voor de hele locatie."""
    tariff = location_tariff(data)
    when = local_now(data, now)
    current = components_at(tariff, when)
    energy = current.get(ENERGY)
    flat = current.get(FLAT)
    return TariffNow(
        energy=round(incl_vat(energy), 4) if energy else None,
        start_fee=round(incl_vat(flat), 4) if flat else 0.0,
        blocking_fee=blocking_fee(tariff),
    )


def blocking_fee(tariff: dict[str, Any] | None) -> BlockingFee | None:
    """Eerste element met een betaalde TIME of PARKING_TIME, samengevat."""
    for element in (tariff or {}).get("elements") or []:
        if not isinstance(element, dict):
            continue
        prices = {
            c.get("type"): incl_vat(c)
            for c in element.get("priceComponents") or []
            if isinstance(c, dict) and c.get("type") in (TIME, PARKING_TIME)
        }
        if not any(price > 0 for price in prices.values()):
            continue
        r = element.get("restrictions") or {}
        window = None
        if r.get("startTime") or r.get("endTime"):
            window = f"{r.get('startTime') or '00:00'}–{r.get('endTime') or '24:00'}"
        days = tuple(r["dayOfWeek"]) if r.get("dayOfWeek") else None
        max_duration = r.get("maxDuration")
        charging = round(prices.get(TIME, 0.0), 4)
        parking = round(prices.get(PARKING_TIME, 0.0), 4)
        return BlockingFee(
            per_hour=max(charging, parking),
            charging_per_hour=charging,
            parking_per_hour=parking,
            free_minutes=int(float(r.get("minDuration") or 0) // 60),
            until_minutes=int(float(max_duration) // 60) if max_duration else None,
            window=window,
            days=days,
        )
    return None


# ----------------------------------------------------------------- helpers


def _matches(r: dict[str, Any], when: datetime, duration_s: float, kwh: float) -> bool:
    return (
        _time_ok(r, when.time())
        and _date_ok(r, when.date())
        and _weekday_ok(r, when.weekday())
        and _range_ok(r.get("minDuration"), r.get("maxDuration"), duration_s)
        and _range_ok(r.get("minKwh"), r.get("maxKwh"), kwh)
    )


def _parse_time(value: Any) -> time | None:
    try:
        hours, minutes = str(value).split(":")[:2]
        return time(int(hours) % 24, int(minutes))
    except (ValueError, TypeError):
        return None


def _time_ok(r: dict[str, Any], now: time) -> bool:
    start = _parse_time(r["startTime"]) if r.get("startTime") else None
    end = _parse_time(r["endTime"]) if r.get("endTime") else None
    if start and end:
        if start < end:
            return start <= now < end
        if start > end:  # over middernacht, bv. 23:00–07:00
            return now >= start or now < end
        return True
    if start:
        return now >= start
    if end:
        return now < end
    return True


def _date_ok(r: dict[str, Any], today: date) -> bool:
    try:
        if r.get("startDate") and today < date.fromisoformat(r["startDate"][:10]):
            return False
        if r.get("endDate") and today >= date.fromisoformat(r["endDate"][:10]):
            return False
    except (TypeError, ValueError):
        return True
    return True


def _weekday_ok(r: dict[str, Any], weekday: int) -> bool:
    days = r.get("dayOfWeek")
    return not days or _WEEKDAYS[weekday] in days


def _range_ok(minimum: Any, maximum: Any, value: float) -> bool:
    """min inclusief, max exclusief (zoals OCPI)."""
    if minimum is not None and value < float(minimum):
        return False
    return not (maximum is not None and value >= float(maximum))


def _euro(value: float) -> str:
    return f"€{value:.2f}".replace(".", ",")


def _duration(minutes: int) -> str:
    if minutes % 60 == 0:
        return f"{minutes // 60} u"
    if minutes > 60:
        return f"{minutes // 60} u {minutes % 60} min"
    return f"{minutes} min"
