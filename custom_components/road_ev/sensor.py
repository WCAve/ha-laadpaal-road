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
    "UNKNOWN": "Onbekend"
}

async def async_setup_entry(hass, entry, async_add_entities):
    """Maak alle sensoren aan voor de geselecteerde laadpaal."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    location_id = entry.data["location_id"]
    device_name = entry.title # Gebruikt de naam die je in de UI hebt opgegeven
    
    _LOGGER.warning("Road.io: Setup gestart voor %s", device_name)

    if not coordinator.data:
        _LOGGER.error("Road.io: Geen data gevonden in de coordinator tijdens setup!")
        return

    # Zoek de locaties op in de data
    raw = coordinator.data
    locations = raw.get("data", []) if isinstance(raw, dict) else raw
    
    if not isinstance(locations, list) or not locations:
        _LOGGER.error("Road.io: Kan geen locatielijst vinden in de ontvangen data.")
        return

    location_data = locations[0]
    evses = location_data.get("evses", [])

    entities = []

    # 1. Algemene Informatie (Diagnostisch)
    entities.append(RoadDiagnosticSensor(coordinator, location_id, device_name, "Aanbieder", "operator.name"))
    entities.append(RoadDiagnosticSensor(coordinator, location_id, device_name, "Coördinaten", "coords"))

    # 2. Per Socket (Status, Vermogen, Prijs)
    for index, _ in enumerate(evses):
        entities.append(RoadStatusSensor(coordinator, location_id, device_name, index))
        entities.append(RoadPowerSensor(coordinator, location_id, device_name, index))
        entities.append(RoadPriceSensor(coordinator, location_id, device_name, index))
        entities.append(RoadDiagnosticSensor(coordinator, location_id, device_name, f"Socket {index + 1} Type", "type", index))

    async_add_entities(entities)
    _LOGGER.warning("Road.io: %s sensoren succesvol toegevoegd.", len(entities))

class RoadBaseEntity(CoordinatorEntity, SensorEntity):
    """Basis klasse die luistert naar updates van de coordinator."""
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

    def _get_loc(self):
        """Haalt veilig de locatiegegevens op uit de coordinator."""
        d = self.coordinator.data
        if not d: return {}
        locs = d.get("data", []) if isinstance(d, dict) else d
        return locs[0] if isinstance(locs, list) and locs else {}

class RoadStatusSensor(RoadBaseEntity):
    """Status van de lader (Vrij/Bezet)."""
    def __init__(self, coordinator, location_id, device_name, index):
        super().__init__(coordinator, location_id, device_name, index)
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
    """Maximaal laadvermogen in kW."""
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, location_id, device_name, index):
        super().__init__(coordinator, location_id, device_name, index)
        self._attr_unique_id = f"road_{location_id}_pwr_{index}"
        self._attr_name = f"Socket {index + 1} Max Vermogen"

    @property
    def native_value(self):
        try: return self._get_loc().get("evses", [])[self.index].get("maxPower")
        except: return None

class RoadPriceSensor(RoadBaseEntity):
    """Prijs per kWh inclusief BTW."""
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR/kWh"

    def __init__(self, coordinator, location_id, device_name, index):
        super().__init__(coordinator, location_id, device_name, index)
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
    """Informatieve sensoren (Aanbieder, Type, Coördinaten)."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, location_id, device_name, label, key, index=None):
        super().__init__(coordinator, location_id, device_name, index)
        self._label = label
        self._key = key
        suffix = f"_{index}" if index is not None else ""
        self._attr_unique_id = f"road_{location_id}_{label.lower().replace(' ', '_')}{suffix}"
        self._attr_name = label

    @property
    def native_value(self):
        loc = self._get_loc()
        if self._key == "operator.name":
            return loc.get("operator", {}).get("name")
        if self._key == "coords":
            c = loc.get("geoLocation", {}).get("coordinates", [])
            return f"{c[1]}, {c[0]}" if len(c) == 2 else None
        if self._key == "type":
            try: return loc.get("evses", [])[self.index]["connectors"][0].get("standard")
            except: return "Onbekend"
        return None