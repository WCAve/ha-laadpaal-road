"""Constanten voor de Road.io (E-flux) integratie."""
from datetime import timedelta
import logging

DOMAIN = "eflux_ev"
_LOGGER = logging.getLogger(__package__)

# Configuratie keys
CONF_LOCATION_ID = "location_id"

# Standaard scan interval (elke 60 seconden)
SCAN_INTERVAL = timedelta(seconds=60)