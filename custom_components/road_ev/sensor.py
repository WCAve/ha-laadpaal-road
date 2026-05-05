"""Sensor platform voor Road.io."""
from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN, CONF_NAME

STATUS_MAP = {
    "AVAILABLE": "Vrij",
    "OCCUPIED": "Bezet",
    "CHARGING": "Bezet",
    "UNAVAILABLE": "Niet beschikbaar/Defect",
    "UNKNOWN": "Niet beschikbaar/Defect"
}

async def async_setup_entry(hass, entry, async_add_entities):
    """Maak de sensoren aan op basis van de coordinator data."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    location_id = entry.data["location_id"]
    custom_name = entry.data.get(CONF_NAME, f"Lader {location_id}")
    
    if not coordinator.data:
        return

    entities = [
        EfluxChargingSensor(coordinator, location_id, custom_name, index)
        for index, _ in enumerate(coordinator.data)
    ]
    
    async_add_entities(entities)

class EfluxChargingSensor(SensorEntity):
    """De fysieke sensor in Home Assistant."""

    # Dit is de cruciale instelling voor moderne Home Assistant naamgeving
    _attr_has_entity_name = True

    def __init__(self, coordinator, location_id, custom_name, index):
        self.coordinator = coordinator
        self.index = index
        
        # De unique_id is onzichtbaar in de UI, maar essentieel voor de database.
        # Dit móét het ID bevatten, anders crasht HA als je een tweede lader toevoegt.
        self._attr_unique_id = f"eflux_{location_id}_{index}"
        
        # Omdat has_entity_name True is, is dit alleen het 'achtervoegsel'
        self._attr_name = f"Socket {index + 1}"
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, location_id)},
            "name": custom_name, # Hier wordt de naam "Uilenweg" gekoppeld
            "manufacturer": "Road.io",
        }

    @property
    def state(self):
        """Vertaal en retourneer de actuele status."""
        try:
            raw_status = self.coordinator.data[self.index].get("status")
            return STATUS_MAP.get(raw_status, "Niet beschikbaar/Defect")
        except (IndexError, KeyError, TypeError):
            return "Niet beschikbaar/Defect"

    @property
    def icon(self):
        """Kies een relevant icoon gebaseerd op de status."""
        if self.state == "Vrij":
            return "mdi:ev-station"
        elif self.state == "Bezet":
            return "mdi:car-electric"
        return "mdi:alert-circle-outline"

    @property
    def available(self):
        """Controleer of de data recent nog is geüpdatet."""
        return self.coordinator.last_update_success