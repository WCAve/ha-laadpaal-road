"""Sensor platform voor Road.io."""
import logging
from homeassistant.components.sensor import (
    SensorEntity, 
    SensorDeviceClass, 
    SensorStateClass
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import UnitOfPower
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STATUS_MAP = {
    "AVAILABLE": "Vrij",
    "OCCUPIED": "Bezet",
    "CHARGING": "Bezet",
    "UNAVAILABLE": "Niet beschikbaar",
}

async def async_setup_entry(hass, entry, async_add_entities):
    """Maak de sensoren aan voor de Road.io lader."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    location_id = entry.data["location_id"]
    device_name = entry.title

    if not coordinator.data:
        await coordinator.async_config_entry_first_refresh()

    evses = coordinator.data.get("evses", [])
    entities = []

    # 1. Diagnostiek (Aanbieder & Locatie)
    entities.append(RoadDiagnosticSensor(coordinator, location_id, device_name, "Aanbieder", "operator"))
    entities.append(RoadDiagnosticSensor(coordinator, location_id, device_name, "Coördinaten", "coords"))
    
    # 2. Centrale Prijs sensor (1 per paal)
    entities.append(RoadLocationPriceSensor(coordinator, location_id, device_name))

    # 3. Per Socket (Status en Vermogen)
    for index, _ in enumerate(evses):
        entities.append(RoadSocketSensor(coordinator, location_id, device_name, index, "status"))
        entities.append(RoadSocketSensor(coordinator, location_id, device_name, index, "power"))

    async_add_entities(entities)

class RoadBaseEntity(CoordinatorEntity, SensorEntity):
    """Basis klasse voor Road entiteiten."""
    _attr_has_entity_name = True
    def __init__(self, coordinator, location_id, device_name, index=None):
        super().__init__(coordinator)
        self.location_id = location_id
        self.device_name = device_name
        self.index = index
        self._attr_device_info = {
            "identifiers": {(DOMAIN, location_id)},
            "name": device_name,
            "manufacturer": "Road.io",
        }

class RoadLocationPriceSensor(RoadBaseEntity):
    """Centrale prijs sensor voor de hele laadpaal."""
    _attr_name = "Prijs"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR/kWh"
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, location_id, device_name):
        super().__init__(coordinator, location_id, device_name)
        self._attr_unique_id = f"road_{location_id}_central_price_final"

    @property
    def native_value(self):
        try:
            evse = self.coordinator.data["evses"][0]
            p = evse["connectors"][0]["tariff"]["elements"][0]["priceComponents"][0]
            return round(p["price"] * (1 + (p.get("vat", 0) / 100)), 4)
        except (KeyError, IndexError, TypeError): return None

class RoadSocketSensor(RoadBaseEntity):
    """Status en Vermogen per socket."""
    def __init__(self, coordinator, location_id, device_name, index, sensor_type):
        super().__init__(coordinator, location_id, device_name, index)
        self._type = sensor_type
        self._attr_unique_id = f"road_{location_id}_{sensor_type}_{index}_final"
        
        if sensor_type == "status":
            self._attr_name = f"Socket {index + 1}"
            self._attr_icon = "mdi:ev-station"
        else: # power
            self._attr_name = f"Socket {index + 1} Max Vermogen"
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
            self._attr_suggested_display_precision = 0

    @property
    def native_value(self):
        try:
            evse = self.coordinator.data["evses"][self.index]
            if self._type == "status":
                return STATUS_MAP.get(evse.get("status"), "Onbekend")
            if self._type == "power":
                val = evse.get("maxPower")
                return int(round(val)) if val is not None else None
        except (KeyError, IndexError, TypeError): return None

class RoadDiagnosticSensor(RoadBaseEntity):
    """Informatieve sensoren."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, coordinator, location_id, device_name, label, key):
        super().__init__(coordinator, location_id, device_name)
        self._key = key
        self._attr_name = label
        self._attr_unique_id = f"road_{location_id}_{label.lower()}_final"

    @property
    def native_value(self):
        d = self.coordinator.data
        if self._key == "operator": return d.get("operator", {}).get("name")
        if self._key == "coords":
            c = d.get("geoLocation", {}).get("coordinates", [])
            return f"{c[1]}, {c[0]}" if len(c) == 2 else None
        return None