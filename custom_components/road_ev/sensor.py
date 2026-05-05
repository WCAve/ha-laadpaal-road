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

_LOGGER = logging.getLogger(__name__)

STATUS_MAP = {
    "AVAILABLE": "Vrij",
    "OCCUPIED": "Bezet",
    "CHARGING": "Bezet",
    "UNAVAILABLE": "Niet beschikbaar",
    "UNKNOWN": "Onbekend"
}

async def async_setup_entry(hass, entry, async_add_entities):
    """Maak alle sensoren aan voor de geselecteerde laadpaal."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    location_id = entry.data["location_id"]
    custom_name = entry.data.get(CONF_NAME, f"Lader {location_id}")
    
    _LOGGER.info("Road.io: Start setup voor %s", custom_name)

    if not coordinator.data:
        _LOGGER.error("Road.io: Geen data in coordinator")
        return

    # Pak de lijst met locaties
    raw = coordinator.data
    locations = raw.get("data", []) if isinstance(raw, dict) else raw
    
    if not locations or not isinstance(locations, list):
        _LOGGER.error("Road.io: Geen locatielijst gevonden")
        return

    location_data = locations[0]
    evses = location_data.get("evses", [])

    entities = []

    # 1. Locatie sensoren
    entities.append(RoadDiagnosticSensor(coordinator, location_id, custom_name, "Aanbieder"))
    entities.append(RoadDiagnosticSensor(coordinator, location_id, custom_name, "Coördinaten"))

    # 2. Per socket sensoren
    for index, _ in enumerate(evses):
        entities.append(RoadStatusSensor(coordinator, location_id, custom_name, index))
        entities.append(RoadPowerSensor(coordinator, location_id, custom_name, index))
        entities.append(RoadPriceSensor(coordinator, location_id, custom_name, index))
        entities.append(RoadDiagnosticSensor(coordinator, location_id, custom_name, f"Socket {index + 1} Type", index))

    async_add_entities(entities)
    _LOGGER.info("Road.io: %s entiteiten toegevoegd", len(entities))

class RoadBaseEntity(SensorEntity):
    """Basis klasse voor Road entiteiten."""
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
        """Haal de eerste locatie veilig op."""
        d = self.coordinator.data
        if not d: return {}
        locs = d.get("data", []) if isinstance(d, dict) else d
        return locs[0] if locs else {}

class RoadStatusSensor(RoadBaseEntity):
    """Status van de lader."""
    def __init__(self, coordinator, location_id, custom_name, index):
        super().__init__(coordinator, location_id, custom_name, index)
        self._attr_unique_id = f"road_{location_id}_status_{index}"
        self._attr_name = f"Socket {index + 1}"

    @property
    def native_value(self):
        try:
            evse = self._get_loc().get("evses", [])[self.index]
            return STATUS_MAP.get(evse.get("status"), "Onbekend")
        except: return "Onbekend"

    @property
    def icon(self):
        return "mdi:ev-station" if self.native_value == "Vrij" else "mdi:car-electric"

class RoadPowerSensor(RoadBaseEntity):
    """Maximaal vermogen."""
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator, location_id, custom_name, index):
        super().__init__(coordinator, location_id, custom_name, index)
        self._attr_unique_id = f"road_{location_id}_pwr_{index}"
        self._attr_name = f"Socket {index + 1} Max Vermogen"

    @property
    def native_value(self):
        try: return self._get_loc().get("evses", [])[self.index].get("maxPower")
        except: return None

class RoadPriceSensor(RoadBaseEntity):
    """Prijs incl BTW."""
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR/kWh"

    def __init__(self, coordinator, location_id, custom_name, index):
        super().__init__(coordinator, location_id, custom_name, index)
        self._attr_unique_id = f"road_{location_id}_prc_{index}"
        self._attr_name = f"Socket {index + 1} Prijs"

    @property
    def native_value(self):
        try:
            evse = self._get_loc().get("evses", [])[self.index]
            p = evse["connectors"][0]["tariff"]["elements"][0]["priceComponents"][0]
            return round(p["price"] * (1 + (p.get("vat", 0) / 100)), 4)
        except: return None

class RoadDiagnosticSensor(RoadBaseEntity):
    """Diagnostische info."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, location_id, custom_name, label, index=None):
        super().__init__(coordinator, location_id, custom_name, index)
        self._label = label
        suffix = f"_{index}" if index is not None else ""
        self._attr_unique_id = f"road_{location_id}_{label.lower().replace(' ', '_')}{suffix}"
        self._attr_name = label

    @property
    def native_value(self):
        loc = self._get_loc()
        if self._label == "Aanbieder":
            return loc.get("operator", {}).get("name")
        if self._label == "Coördinaten":
            c = loc.get("geoLocation", {}).get("coordinates", [])
            return f"{c[1]}, {c[0]}" if len(c) == 2 else None
        if "Type" in self._label:
            try: return loc.get("evses", [])[self.index]["connectors"][0].get("standard")
            except: return "Onbekend"
        return None