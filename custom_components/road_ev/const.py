"""Constanten voor de Road.io (E-flux) integratie."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "road_ev"

CONF_LOCATION_ID: Final = "location_id"
CONF_NAME: Final = "name"

DEFAULT_NAME: Final = "Mijn Laadpaal"
SCAN_INTERVAL: Final = timedelta(seconds=60)

API_URL: Final = "https://api.road.io/1/map/locations"
API_TIMEOUT: Final = 10

MANUFACTURER: Final = "Road.io"
