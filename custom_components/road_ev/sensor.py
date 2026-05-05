"""Sensor platform voor Road.io."""
import logging
from homeassistant.components.sensor import (
    SensorEntity, 
    SensorDeviceClass, 
    SensorStateClass
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import UnitOfPower
from .const import DOMAIN, CONF_NAME

# We forceren het log-niveau naar INFO voor deze module
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)

STATUS_MAP = {
    "AVAILABLE": "Vrij",
    "OCCUPIED": "Bezet",
    "CHARGING": "Bezet",
    "UNAVAILABLE": "Niet beschikbaar",
    "UNKNOWN": "Onbekend"
}

async def async_setup_entry(hass, entry, async_add_entities):
    """Maak alle sensoren aan."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    location_id = entry.data["location_id"]
    custom_name = entry.data.get(CONF_NAME, f"Lader {location_id}")
    
    _LOGGER.info("--- START ROAD.IO SETUP ---")
    _LOGGER.info("Data in coordinator: %s", coordinator.data)

    entities = []

    # TEST SENSOR: Deze moet ALTIJD verschijnen als de file geladen wordt
    entities.append(RoadDebugSensor(coordinator, location_id, custom_name))

    if not coordinator.data:
        _LOGGER.warning("Setup gestopt: Coordinator heeft geen data.")
        async_add_entities(entities)
        return

    # Data extractie
    raw = coordinator.data
    locations = raw.get("data", []) if isinstance(raw, dict) else raw
    
    if not isinstance(locations, list) or len(locations) == 0:
        _LOGGER.warning("Setup gestopt: Geen locatielijst gevonden in data.")
        async_add_entities(entities)
        return

    loc = locations[0]
    evses = loc.get("evses", [])
    _LOGGER.info("Aantal sockets gevonden: %s", len(evses))

    # 1. Locatie info
    op_name = loc.get("operator", {}).get("name")
    if op_name:
        entities.append(RoadDiagnosticSensor(coordinator, location_id, custom_name, "Aanbieder", op_name))

    # 2. Per socket
    for i, _ in enumerate(evses):
        entities.append(RoadStatusSensor(coordinator, location_id, custom_name, i))
        entities.append(RoadPowerSensor(coordinator, location_id, custom_name, i))
        entities.append(RoadPriceSensor(coordinator, location_id, custom_name, i))

    async_add_entities(entities)
    _LOGGER.info("Setup voltooid. %s entities toegevoegd.", len(entities))

class RoadBaseEntity(SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, location_id, custom_name, index=None):
        self.coordinator = coordinator
        self.location_id = location_id
        self.index = index
        self._attr_device_info = {
            "identifiers": {(DOMAIN, location_id)},
            "name": custom_name,
            "manufacturer": "Road.io",
        }

    def _get_loc(self):
        d = self.coordinator.data
        return (d.get("data", [{}])[0] if isinstance(d, dict) else d[0]) if d else {}

class RoadDebugSensor(RoadBaseEntity):
    """Deze sensor is er alleen om te testen of de integratie laadt."""
    _attr_name = "Debug Status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    @property
    def native_value(self):
        return "Bestand Geladen"

class RoadStatusSensor(RoadBaseEntity):
    def __init__(self, coordinator, location_id, custom_name, index):
        super().__init__(coordinator, location_id, custom_name, index)
        self._attr_unique_id = f"road_{location_id}_status_{index}"
        self._attr_name = f"Socket {index + 1}"
    @property
    def native_value(self):
        try:
            s = self._get_loc()["evses"][self.index].get("status")
            return STATUS_MAP.get(s, "Onbekend")
        except: return "Fout"

class RoadPowerSensor(RoadBaseEntity):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    def __init__(self, coordinator, location_id, custom_name, index):
        super().__init__(coordinator, location_id, custom_name, index)
        self._attr_unique_id = f"road_{location_id}_pwr_{index}"
        self._attr_name = f"Socket {index + 1} Max Vermogen"
    @property
    def native_value(self):
        try: return self._get_loc()["evses"][self.index].get("maxPower")
        except: return None

class RoadPriceSensor(RoadBaseEntity):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR/kWh"
    def __init__(self, coordinator, location_id, custom_name, index):
        super().__init__(coordinator, location_id, custom_name, index)
        self._attr_unique_id = f"road_{location_id}_prc_{index}"
        self._attr_name = f"Socket {index + 1} Prijs"
    @property
    def native_value(self):
        try:
            evse = self._get_loc()["evses"][self.index]
            p = evse["connectors"][0]["tariff"]["elements"][0]["priceComponents"][0]
            return round(p["price"] * (1 + (p.get("vat", 0)/100)), 4)
        except: return None

class RoadDiagnosticSensor(RoadBaseEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, coordinator, location_id, custom_name, label, val):
        super().__init__(coordinator, location_id, custom_name)
        self._attr_unique_id = f"road_{location_id}_{label.lower()}"
        self._attr_name = label
        self._attr_native_value = val