"""Sensor platform voor Road.io."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import UnitOfPower, CURRENCY_EURO
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
    
    if not coordinator.data or not isinstance(coordinator.data, list):
        return

    # We pakken de data van de eerste locatie in de lijst
    location_data = coordinator.data[0]
    evses = location_data.get("evses", [])

    entities = []

    # 1. Locatie-brede diagnostische sensoren (1 per apparaat)
    entities.append(RoadDiagnosticSensor(coordinator, location_id, custom_name, "Aanbieder", location_data.get("operator", {}).get("name")))
    
    coords = location_data.get("geoLocation", {}).get("coordinates", [])
    if len(coords) == 2:
        entities.append(RoadDiagnosticSensor(coordinator, location_id, custom_name, "Coördinaten", f"{coords[1]}, {coords[0]}"))

    # 2. EVSE-specifieke sensoren (per socket/stekker)
    for index, evse in enumerate(evses):
        # Status sensor (bestaand)
        entities.append(RoadStatusSensor(coordinator, location_id, custom_name, index))
        
        # Max Vermogen sensor
        max_power = evse.get("maxPower")
        entities.append(RoadPowerSensor(coordinator, location_id, custom_name, index, max_power))
        
        # Prijs sensor (incl BTW)
        try:
            connector = evse.get("connectors", [{}])[0]
            price_data = connector.get("tariff", {}).get("elements", [{}])[0].get("priceComponents", [{}])[0]
            if price_data:
                base_price = price_data.get("price", 0)
                vat_rate = price_data.get("vat", 0)
                total_price = round(base_price * (1 + (vat_rate / 100)), 4)
                entities.append(RoadPriceSensor(coordinator, location_id, custom_name, index, total_price))
        except (IndexError, KeyError):
            pass

        # Aansluiting type (Diagnostic)
        try:
            standard = evse.get("connectors", [{}])[0].get("standard", "Onbekend")
            entities.append(RoadDiagnosticSensor(coordinator, location_id, custom_name, f"Socket {index + 1} Type", standard, index))
        except IndexError:
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
    """Sensor voor de laadstatus."""
    def __init__(self, coordinator, location_id, custom_name, index):
        super().__init__(coordinator, location_id, custom_name, index)
        self.index = index
        self._attr_unique_id = f"road_{location_id}_status_{index}"
        self._attr_name = f"Socket {index + 1}"

    @property
    def state(self):
        try:
            raw = self.coordinator.data[0]["evses"][self.index].get("status")
            return STATUS_MAP.get(raw, "Onbekend")
        except (IndexError, KeyError): return "Onbekend"

    @property
    def icon(self):
        return "mdi:ev-station" if self.state == "Vrij" else "mdi:car-electric"

class RoadPowerSensor(RoadBaseEntity):
    """Sensor voor maximaal vermogen."""
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator, location_id, custom_name, index, value):
        super().__init__(coordinator, location_id, custom_name, index)
        self._attr_unique_id = f"road_{location_id}_power_{index}"
        self._attr_name = f"Socket {index + 1} Max Vermogen"
        self._attr_native_value = value

class RoadPriceSensor(RoadBaseEntity):
    """Sensor voor de prijs per kWh incl BTW."""
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
    """Sensor voor diagnostische informatie."""
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