"""Constanten voor de Road.io (E-flux) integratie."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "road_ev"

CONF_LOCATION_ID: Final = "location_id"
CONF_NAME: Final = "name"

DEFAULT_NAME: Final = "Mijn Laadpaal"
SCAN_INTERVAL: Final = timedelta(seconds=60)

API_BASE_URL: Final = "https://api.road.io/1/map/"
API_TIMEOUT: Final = 10

MANUFACTURER: Final = "Road.io"

# Laadpaal zoeken bij het toevoegen
CONF_LOCATION: Final = "location"
SEARCH_RADIUS_DEFAULT: Final = 500
SEARCH_RADIUS_MIN: Final = 100
SEARCH_RADIUS_MAX: Final = 3000
SEARCH_MAX_RESULTS: Final = 50
CONF_ADDRESS: Final = "address"

# Adres opzoeken (OpenStreetMap Nominatim). Moet uit te zetten/te vervangen
# zijn als OSM daarom vraagt: pas dan alleen deze URL aan.
GEOCODE_URL: Final = "https://nominatim.openstreetmap.org/search"
GEOCODE_USER_AGENT: Final = (
    "ha-road-ev (Home Assistant integration; https://github.com/WCAve/ha-laadpaal-road)"
)
GEOCODE_TIMEOUT: Final = 10

# Opties (Configureren) voor de "Laadwens" meldingen
CONF_NOTIFY_TARGETS: Final = "notify_targets"
CONF_DISARM_AFTER_NOTIFY: Final = "disarm_after_notify"
CONF_NOTIFY_WHEN_TAKEN: Final = "notify_when_taken"
CONF_EXPIRE_HOURS: Final = "expire_hours"
CONF_MIN_FREE_MINUTES: Final = "min_free_minutes"
CONF_PERSON: Final = "person"
CONF_DISARM_OTHERS: Final = "disarm_others"
CONF_ANDROID_AUTO: Final = "android_auto"
CONF_NOTIFY_PRICE_CHANGE: Final = "notify_price_change"

DEFAULT_OPTIONS: Final[dict] = {
    CONF_NOTIFY_TARGETS: [],
    CONF_DISARM_AFTER_NOTIFY: True,
    CONF_NOTIFY_WHEN_TAKEN: True,
    CONF_EXPIRE_HOURS: 0,
    CONF_MIN_FREE_MINUTES: 0,
    CONF_DISARM_OTHERS: True,
    CONF_ANDROID_AUTO: False,
    CONF_NOTIFY_PRICE_CHANGE: True,
}

# Speciaal meldingsdoel: de meldingen in Home Assistant zelf.
TARGET_PERSISTENT: Final = "persistent_notification"

# Hoe lang we na een "vrij"-melding blijven kijken of de paal weer bezet raakt.
FOLLOW_UP_WINDOW: Final = timedelta(minutes=30)
# Binnen deze afstand van de paal ga je ervan uit dat jij de paal bezet.
ARRIVAL_RADIUS_M: Final = 200

# Bel je meerdere palen tegelijk aan en is er één al vrij, dan tellen
# laadwensen die binnen deze tijd daarna worden aangezet als "al geregeld".
GROUP_ARM_GRACE: Final = timedelta(seconds=10)

# Reparatiemeldingen: pas melden als Road.io zo lang onbereikbaar is.
UNREACHABLE_REPAIR_AFTER: Final = timedelta(minutes=30)

# Android meldingskanaal voor laadwens-meldingen (ook gebruikt voor Android Auto).
NOTIFY_CHANNEL: Final = "Laadpalen"

# mobile_app actie-id voor de "Stop" knop in een melding.
ACTION_STOP_PREFIX: Final = "ROAD_EV_STOP_"

# Frontend kaart
CARD_URL: Final = f"/{DOMAIN}/road-ev-card.js"
