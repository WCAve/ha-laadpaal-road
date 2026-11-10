"""Hulpfuncties om de ruwe locatie-data van de API uit te lezen."""

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
