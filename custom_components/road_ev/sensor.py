"""Sensor platform voor Road.io."""
import logging
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
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
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    location_id = entry.data["location_id"]
    device_name = entry.title

    # Wacht op eerste data als die er nog niet is
    if not coordinator.data:
        await coordinator.async_config_entry_first_refresh()

    evses = coordinator.data.get("evses", [])
    entities = []

    # 1. Diagnostische Sensoren (Location level)
    entities.append(RoadInfoSensor(coordinator, location_id, device_name, "Aanbieder", "operator"))
    entities.append(RoadInfoSensor(coordinator, location_id, device_name, "Coördinaten", "coords"))

    # 2. Per Socket Sensoren
    for index, _ in enumerate(evses):
        entities.append(RoadSocketSensor(coordinator, location_id, device_name, index, "status"))
        entities.append(RoadSocketSensor(coordinator, location_id, device_name, index, "power"))
        entities.append(RoadSocketSensor(coordinator, location_id, device_name, index, "price"))

    async_add_entities(entities)

class RoadBaseEntity(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, location_id, device_name):
        super().__init__(coordinator)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, location_id)},
            "name": device_name,
            "manufacturer": "Road.io",
        }

class RoadInfoSensor(RoadBaseEntity):
    """Sensoren voor Aanbieder en Coördinaten."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, location_id, device_name, label, key):
        super().__init__(coordinator, location_id, device_name)
        self._key = key
        self._attr_name = label
        self._attr_unique_id = f"road_{location_id}_{label.lower()}"

    @property
    def native_value(self):
        if self._key == "operator":
            return self.coordinator.data.get("operator", {}).get("name")
        if self._key == "coords":
            c = self.coordinator.data.get("geoLocation", {}).get("coordinates", [])
            return f"{c[1]}, {c[0]}" if len(c) == 2 else None
        return None

class RoadSocketSensor(RoadBaseEntity):
    """Sensoren voor Status, Vermogen en Prijs per socket."""
    def __init__(self, coordinator, location_id, device_name, index, sensor_type):
        super().__init__(coordinator, location_id, device_name)
        self._index = index
        self._type = sensor_type
        
        types = {
            "status": [f"Socket {index+1}", None, "mdi:ev-station"],
            "power": [f"Socket {index+1} Max Vermogen", SensorDeviceClass.POWER, "mdi:lightning-bolt"],
            "price": [f"Socket {index+1} Prijs", SensorDeviceClass.MONETARY, "mdi:cash"]
        }
        
        self._attr_name = types[sensor_type][0]
        self._attr_device_class = types[sensor_type][1]
        self._attr_icon = types[sensor_type][2]
        self._attr_unique_id = f"road_{location_id}_{sensor_type}_{index}"
        
        if sensor_type == "power": self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
        if sensor_type == "price": self._attr_native_unit_of_measurement = "EUR/kWh"

    @property
    def native_value(self):
        try:
            evse = self.coordinator.data["evses"][self._index]
            if self._type == "status":
                return STATUS_MAP.get(evse.get("status"), "Onbekend")
            if self._type == "power":
                return evse.get("maxPower")
            if self._type == "price":
                p = evse["connectors"][0]["tariff"]["elements"][0]["priceComponents"][0]
                return round(p["price"] * (1 + (p.get("vat", 0) / 100)), 4)
        except: return None
        return None