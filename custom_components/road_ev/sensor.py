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
    
    # Debug logging om te zien wat er binnenkomt
    _LOGGER.debug("Road.io data setup voor: %s", custom_name)

    if not coordinator.data:
        _LOGGER.error("Geen data ontvangen van coordinator voor %s", custom_name)
        return

    # Probeer de lijst met locaties te vinden
    locations = []
    if isinstance(coordinator.data, dict):
        locations = coordinator.data.get("data", [])
    elif isinstance(coordinator.data, list):
        locations = coordinator.data

    if not locations:
        _LOGGER.warning("Geen locatiegegevens gevonden in Road.io data")
        return

    location_data = locations[0]
    evses = location_data.get("evses", [])

    entities = []

    # 1. Locatie-brede sensoren
    entities.append(RoadDiagnosticSensor(coordinator, location_id, custom_name, "Aanbieder", "operator.name"))
    entities.append(RoadDiagnosticSensor(coordinator, location_id, custom_name, "Coördinaten", "geoLocation.coordinates"))

    # 2. Per socket sensoren
    for index, _ in enumerate(evses):
        entities.append(RoadStatusSensor(coordinator, location_id, custom_name, index))
        entities.append(RoadPowerSensor(coordinator, location_id, custom_name, index))
        entities.append(RoadPriceSensor(coordinator, location_id, custom_name, index))
        entities.append(RoadDiagnosticSensor(coordinator, location_id, custom_name, f"Socket {index + 1} Type", f"evses.{index}.connectors.0.standard", index))

    async_add_entities(entities)

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

    def _get_location_data(self):
        """Hulpfunctie om veilig bij de data te komen."""
        data = self.coordinator.data
        if isinstance(data, dict):
            return data.get("data", [{}])[0]
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return {}

class RoadStatusSensor(RoadBaseEntity):
    """Sensor voor de laadstatus."""
    def __init__(self, coordinator, location_id, custom_name, index):
        super().__init__(coordinator, location_id, custom_name, index)
        self._attr_unique_id = f"road_{location_id}_status_{index}"
        self._attr_name = f"Socket {index + 1}"

    @property
    def native_value(self):
        try:
            evse = self._get_location_data().get("evses", [])[self.index]
            return STATUS_MAP.get(evse.get("status"), "Onbekend")
        except (IndexError, KeyError): return "Onbekend"

    @property
    def icon(self):
        return "mdi:ev-station" if self.native_value == "Vrij" else "mdi:car-electric"

class RoadPowerSensor(RoadBaseEntity):
    """Sensor voor maximaal vermogen."""
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator, location_id, custom_name, index):
        super().__init__(coordinator, location_id, custom_name, index)
        self._attr_unique_id = f"road_{location_id}_power_{index}"
        self._attr_name = f"Socket {index + 1} Max Vermogen"

    @property
    def native_value(self):
        try:
            return self._get_location_data().get("evses", [])[self.index].get("maxPower")
        except (IndexError, KeyError): return None

class RoadPriceSensor(RoadBaseEntity):
    """Sensor voor prijs per kWh."""
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR/kWh"

    def __init__(self, coordinator, location_id, custom_name, index):
        super().__init__(coordinator, location_id, custom_name, index)
        self._attr_unique_id = f"road_{location_id}_price_{index}"
        self._attr_name = f"Socket {index + 1} Prijs"

    @property
    def native_value(self):
        try:
            evse = self._get_location_data().get("evses", [])[self.index]
            price_comp = evse["connectors"][0]["tariff"]["elements"][0]["priceComponents"][0]
            total = price_comp["price"] * (1 + (price_comp.get("vat", 0) / 100))
            return round(total, 4)
        except (IndexError, KeyError, TypeError): return None

class RoadDiagnosticSensor(RoadBaseEntity):
    """Sensor voor info zoals Aanbieder of Coördinaten."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, location_id, custom_name, label, data_path, index=None):
        super().__init__(coordinator, location_id, custom_name, index)
        self._label = label
        self._data_path = data_path
        suffix = f"_{index}" if index is not None else ""
        self._attr_unique_id = f"road_{location_id}_{label.lower().replace(' ', '_')}{suffix}"
        self._attr_name = label

    @property
    def native_value(self):
        data = self._get_location_data()
        if self._label == "Aanbieder":
            return data.get("operator", {}).get("name")
        if self._label == "Coördinaten":
            coords = data.get("geoLocation", {}).get("coordinates", [])
            return f"{coords[1]}, {coords[0]}" if len(coords) == 2 else None
        if "Type" in self._label:
            try:
                return data.get("evses", [])[self.index]["connectors"][0].get("standard")
            except (IndexError, KeyError): return "Onbekend"
        return None