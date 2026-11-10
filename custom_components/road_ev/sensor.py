"""Sensor platform voor Road.io.

Let op: de namen en unique_id's van deze sensoren zijn bewust gelijk gebleven
aan v2.1, zodat bestaande entity_id's (en de radar-template, die zoekt naar
``*_beschikbaarheid`` en ``*_coordinaten``) blijven werken.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RoadConfigEntry
from .coordinator import RoadDataUpdateCoordinator
from .data import evses, free_count, price_per_kwh
from .entity import RoadEntity

_LOGGER = logging.getLogger(__name__)

# Coordinator haalt alles centraal op; de sensoren doen zelf geen requests.
PARALLEL_UPDATES = 0

STATUS_UNKNOWN = "Onbekend"
STATUS_MAP: dict[str, str] = {
    "AVAILABLE": "Vrij",
    "OCCUPIED": "Bezet",
    "CHARGING": "Bezet",
    "BLOCKED": "Geblokkeerd",
    "RESERVED": "Gereserveerd",
    "UNAVAILABLE": "Niet beschikbaar",
    "INOPERATIVE": "Buiten gebruik",
    "OUTOFORDER": "Buiten gebruik",
    "PLANNED": "Gepland",
    "REMOVED": "Verwijderd",
    "UNKNOWN": STATUS_UNKNOWN,
}
STATUS_OPTIONS: list[str] = sorted({*STATUS_MAP.values(), STATUS_UNKNOWN})


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RoadConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Maak de sensoren aan voor de Road.io lader."""
    coordinator = entry.runtime_data.coordinator

    async_add_entities(
        [
            # 1. Diagnostiek (Aanbieder & Locatie)
            RoadOperatorSensor(coordinator),
            RoadCoordinatesSensor(coordinator),
            # 2. Centrale prijs sensor
            RoadLocationPriceSensor(coordinator),
            # 3. De overkoepelende beschikbaarheid (aantal sockets vrij)
            RoadAvailabilitySensor(coordinator),
        ]
    )

    # 4. Per socket (status en vermogen). Komen er later sockets bij, dan
    #    worden die automatisch toegevoegd zonder herladen.
    known_sockets: set[int] = set()

    @callback
    def _async_add_new_sockets() -> None:
        new_entities: list[SensorEntity] = []
        for index in range(len(evses(coordinator.data))):
            if index in known_sockets:
                continue
            known_sockets.add(index)
            new_entities.append(RoadSocketStatusSensor(coordinator, index))
            new_entities.append(RoadSocketPowerSensor(coordinator, index))
        if new_entities:
            async_add_entities(new_entities)

    _async_add_new_sockets()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_sockets))


class RoadBaseEntity(RoadEntity, SensorEntity):
    """Basisklasse voor Road sensoren."""


class RoadLocationPriceSensor(RoadBaseEntity):
    """Centrale prijs sensor voor de hele laadpaal (incl. btw)."""

    # Geen SensorDeviceClass.MONETARY: die accepteert alleen een valuta als
    # eenheid (bv. "EUR"), niet "EUR/kWh", en gaf daarom een waarschuwing.
    _attr_name = "Prijs"
    _attr_translation_key = "price"
    _attr_native_unit_of_measurement = "EUR/kWh"
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator: RoadDataUpdateCoordinator) -> None:
        """Initialiseer de prijs sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"road_{self.location_id}_central_price_final"

    @property
    def native_value(self) -> float | None:
        """Prijs per kWh van het eerste tarief van de eerste socket."""
        return price_per_kwh(self.coordinator.data)


class RoadAvailabilitySensor(RoadBaseEntity):
    """Samenvattende sensor voor de beschikbaarheid van de hele paal."""

    _attr_name = "Beschikbaarheid"
    # translation_key: hiermee vindt de kaart deze sensor terug.
    _attr_translation_key = "availability"
    _attr_icon = "mdi:ev-plug-type2"

    def __init__(self, coordinator: RoadDataUpdateCoordinator) -> None:
        """Initialiseer de beschikbaarheid sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"road_{self.location_id}_availability"

    def _counts(self) -> tuple[int, int]:
        return free_count(self.coordinator.data), len(self.evses)

    @property
    def native_value(self) -> str:
        """Toon de status als 'X van de Y vrij'."""
        free, total = self._counts()
        if total == 0:
            return "Geen sockets"
        return f"{free} van de {total} vrij"

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        """Getallen voor automatiseringen en de radar-template."""
        free, total = self._counts()
        return {"vrije_plekken": free, "totale_plekken": total}


class RoadSocketBaseSensor(RoadBaseEntity):
    """Basis voor sensoren die bij één socket horen."""

    def __init__(self, coordinator: RoadDataUpdateCoordinator, index: int) -> None:
        """Initialiseer een socket sensor."""
        super().__init__(coordinator)
        self.index = index

    @property
    def evse(self) -> dict[str, Any] | None:
        """De data van deze socket, of None als hij (nu) niet bestaat."""
        evses = self.evses
        return evses[self.index] if self.index < len(evses) else None

    @property
    def available(self) -> bool:
        """Niet beschikbaar als de socket uit de API-data verdwenen is."""
        return super().available and self.evse is not None


class RoadSocketStatusSensor(RoadSocketBaseSensor):
    """Status van één socket."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUS_OPTIONS
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator: RoadDataUpdateCoordinator, index: int) -> None:
        """Initialiseer de status sensor."""
        super().__init__(coordinator, index)
        self._attr_name = f"Socket {index + 1}"
        self._attr_unique_id = f"road_{self.location_id}_status_{index}_final"

    @property
    def native_value(self) -> str | None:
        """Vertaalde status, of 'Onbekend' voor een status die we niet kennen."""
        if (evse := self.evse) is None:
            return None
        status = evse.get("status")
        if status not in STATUS_MAP:
            _LOGGER.debug("Onbekende socket status van Road.io: %s", status)
        return STATUS_MAP.get(status, STATUS_UNKNOWN)


class RoadSocketPowerSensor(RoadSocketBaseSensor):
    """Maximaal vermogen van één socket."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: RoadDataUpdateCoordinator, index: int) -> None:
        """Initialiseer de vermogen sensor."""
        super().__init__(coordinator, index)
        self._attr_name = f"Socket {index + 1} Max Vermogen"
        self._attr_unique_id = f"road_{self.location_id}_power_{index}_final"

    @property
    def native_value(self) -> int | None:
        """Maximaal vermogen in kW."""
        if (evse := self.evse) is None:
            return None
        val = evse.get("maxPower")
        try:
            return int(round(val)) if val is not None else None
        except (TypeError, ValueError):
            return None


class RoadOperatorSensor(RoadBaseEntity):
    """Naam van de aanbieder (CPO)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Aanbieder"

    def __init__(self, coordinator: RoadDataUpdateCoordinator) -> None:
        """Initialiseer de aanbieder sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"road_{self.location_id}_aanbieder_final"

    @property
    def native_value(self) -> str | None:
        """Naam van de operator."""
        operator = (self.coordinator.data or {}).get("operator") or {}
        return operator.get("name")


class RoadCoordinatesSensor(RoadBaseEntity):
    """Coördinaten van de locatie als 'lat, lon'."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Coördinaten"
    _attr_translation_key = "coordinates"

    def __init__(self, coordinator: RoadDataUpdateCoordinator) -> None:
        """Initialiseer de coördinaten sensor."""
        super().__init__(coordinator)
        # Met 'ö', precies zoals v2.1 hem aanmaakte.
        self._attr_unique_id = f"road_{self.location_id}_coördinaten_final"

    @property
    def native_value(self) -> str | None:
        """Coördinaten in de vorm 'lat, lon' (de API levert [lon, lat])."""
        geo = (self.coordinator.data or {}).get("geoLocation") or {}
        coords = geo.get("coordinates") or []
        if len(coords) != 2:
            return None
        return f"{coords[1]}, {coords[0]}"
