"""Hulpfuncties om de ruwe Road.io locatie-data uit te lezen."""

from __future__ import annotations

from typing import Any


def evses(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Lijst met sockets (EVSE's), of een lege lijst."""
    if not data:
        return []
    result = data.get("evses")
    return result if isinstance(result, list) else []


def free_count(data: dict[str, Any] | None) -> int:
    """Aantal sockets met status AVAILABLE."""
    return sum(1 for evse in evses(data) if evse.get("status") == "AVAILABLE")


def price_per_kwh(data: dict[str, Any] | None) -> float | None:
    """Prijs per kWh incl. btw van het eerste tarief van de eerste socket."""
    try:
        evse = evses(data)[0]
        p = evse["connectors"][0]["tariff"]["elements"][0]["priceComponents"][0]
        return round(p["price"] * (1 + (p.get("vat", 0) / 100)), 4)
    except (KeyError, IndexError, TypeError):
        return None


def coordinates(data: dict[str, Any] | None) -> tuple[float, float] | None:
    """(lat, lon) van de locatie; de API levert [lon, lat]."""
    geo = (data or {}).get("geoLocation") or {}
    coords = geo.get("coordinates") or []
    if len(coords) != 2:
        return None
    try:
        return float(coords[1]), float(coords[0])
    except (TypeError, ValueError):
        return None
