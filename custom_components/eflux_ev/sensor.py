from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN

STATUS_MAP = {
    "AVAILABLE": "Vrij",
    "OCCUPIED": "Bezet",
    "CHARGING": "Bezet",
    "UNAVAILABLE": "Niet beschikbaar/Defect",
    "UNKNOWN": "Niet beschikbaar/Defect"
}

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    location_id = entry.data["location_id"]
    
    entities = []
    for index, evse in enumerate(coordinator.data):
        entities.append(EfluxSensor(coordinator, location_id, index))
    
    async_add_entities(entities)

class EfluxSensor(SensorEntity):
    def __init__(self, coordinator, location_id, index):
        self.coordinator = coordinator
        self.index = index
        self._attr_unique_id = f"{location_id}_{index}"
        self._attr_name = f"Laadpunt {index + 1}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, location_id)},
            "name": f"Road.io Lader {location_id}",
        }

    @property
    def state(self):
        try:
            raw = self.coordinator.data[self.index].get("status")
            return STATUS_MAP.get(raw, "Niet beschikbaar/Defect")
        except:
            return "Niet beschikbaar/Defect"

    @property
    def icon(self):
        return "mdi:ev-station" if self.state == "Vrij" else "mdi:ev-plug-charging"