"""Sensor platform voor Road.io."""
from homeassistant.components.sensor import (
    SensorEntity, 
    SensorDeviceClass, 
    SensorStateClass
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import UnitOfPower
from .const import DOMAIN, CONF_NAME

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
    
    # Robuuste data-extractie: check of het een dict is met een 'data' key, of direct een lijst
    raw_data = coordinator.data
    locations = []
    if isinstance(raw_data, dict):
        locations = raw_data.get("data", [])
    elif isinstance(raw_data, list):
        locations = raw_data

    if not locations:
        return

    # We pakken de eerste locatie uit de resultaten
    location_data = locations[0]
    evses = location_data.get("evses", [])

    entities = []

    # 1. Locatie-brede sensoren
    operator_name = location_data.get("operator", {}).get("name")
    if operator_name:
        entities.append(RoadDiagnosticSensor(coordinator, location_id, custom_name, "Aanbieder", operator_name))
    
    coords = location_data.get("geoLocation", {}).get("coordinates", [])
    if len(coords) == 2:
        entities.append(RoadDiagnosticSensor(coordinator, location_id, custom_name, "Coördinaten", f"{coords[1]}, {coords[0]}"))

    # 2. Per socket sensoren
    for index, evse in enumerate(evses):
        entities.append(RoadStatusSensor(coordinator, location_id, custom_name, index))
        
        max_power = evse.get("maxPower")
        if max_power is not None:
            entities.append(RoadPowerSensor(coordinator, location_id, custom_name, index, max_power))
        
        try:
            connector = evse.get("connectors", [{}])[0]
            tariff = connector.get("tariff", {}).get("elements", [{}])[0]
            price_comp = tariff.get("priceComponents", [{}])[0]
            
            if price_comp:
                base_price = price_comp.get("price", 0)
                vat_rate = price_comp.get("vat", 0)
                total_price = round(base_price * (1 + (vat_rate / 100)), 4)
                entities.append(RoadPriceSensor(coordinator, location_id, custom_name, index, total_price))
        except (IndexError, KeyError, TypeError):
            pass

        try:
            standard = evse.get("connectors", [{}])[0].get("standard")
            if standard:
                entities.append(RoadDiagnosticSensor(coordinator, location_id, custom_name, f"Socket {index + 1} Type", standard, index))
        except (IndexError, KeyError):
            pass

    async_add_entities(entities)

class RoadBaseEntity(SensorEntity):
    """Basis klasse voor Road entiteiten."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, location_id, custom_name, index=None):
        self.coordinator = coordinator
        self.location_id = location_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, location_id)},
            "name": custom_name,
            "manufacturer": "Road.io",
        }

class RoadStatusSensor(RoadBaseEntity):
    """Sensor voor de actuele laadstatus."""
    def __init__(self, coordinator, location_id, custom_name, index):
        super().__init__(coordinator, location_id, custom_name, index)
        self.index = index
        self._attr_unique_id = f"road_{location_id}_status_{index}"
        self._attr_name = f"Socket {index + 1}"

    @property
    def native_value(self):
        try:
            data = self.coordinator.data
            locations = data.get("data", []) if isinstance(data, dict) else data
            raw = locations[0]["evses"][self.index].get("status")
            return STATUS_MAP.get(raw, "Onbekend")
        except (IndexError, KeyError, TypeError):
            return "Onbekend"

    @property
    def icon(self):
        return "mdi:ev-station" if self.native_value == "Vrij" else "mdi:car-electric"

class RoadPowerSensor(RoadBaseEntity):
    """Sensor voor het maximale vermogen."""
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, location_id, custom_name, index, value):
        super().__init__(coordinator, location_id, custom_name, index)
        self._attr_unique_id = f"road_{location_id}_power_{index}"
        self._attr_name = f"Socket {index + 1} Max Vermogen"
        self._attr_native_value = value

class RoadPriceSensor(RoadBaseEntity):
    """Sensor voor de prijs per kWh inclusief BTW."""
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, location_id, custom_name, index, value):
        super().__init__(coordinator, location_id, custom_name, index)
        self._attr_unique_id = f"road_{location_id}_price_{index}"
        self._attr_name = f"Socket {index + 1} Prijs"
        self._attr_native_value = value
        self._attr_icon = "mdi:cash-multiple"

class RoadDiagnosticSensor(RoadBaseEntity):
    """Sensor voor statische diagnostische informatie."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, location_id, custom_name, label, value, index=None):
        super().__init__(coordinator, location_id, custom_name, index)
        suffix = f"_{index}" if index is not None else ""
        self._attr_unique_id = f"road_{location_id}_{label.lower().replace(' ', '_')}{suffix}"
        self._attr_name = label
        self._attr_native_value = value
        
        if "Type" in label: self._attr_icon = "mdi:vector-point"
        elif "Aanbieder" in label: self._attr_icon = "mdi:factory"
        elif "Coördinaten" in label: self._attr_icon = "mdi:map-marker"