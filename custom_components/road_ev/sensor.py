"""Sensor platform voor Road.io.

Let op: de unique_id's van deze sensoren zijn bewust gelijk gebleven aan v2.1,
zodat bestaande entity_id's (en de radar-template) blijven werken.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from . import RoadConfigEntry
from .const import DOMAIN
from .coordinator import RoadDataUpdateCoordinator
from .data import evses, free_count
from .entity import RoadEntity
from .tariff import evaluate, tariffs_differ

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
    _async_clear_old_availability_name(hass, entry)

    async_add_entities(
        [
            # 1. Diagnostiek (Aanbieder & Locatie)
            RoadOperatorSensor(coordinator),
            RoadCoordinatesSensor(coordinator),
            # 2. Centrale prijs sensor
            RoadLocationPriceSensor(coordinator),
            # 3. De overkoepelende beschikbaarheid (aantal sockets vrij)
            RoadAvailabilitySensor(coordinator),
            # 4. Aantal vrije sockets als getal, met lange-termijn statistiek
            #    (voor "meestal vrij om..." op de kaart).
            RoadFreeSocketsSensor(coordinator),
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

    # 5. Starttarief en blokkeertarief: alleen als de paal die heeft (geen
    #    stapel sensoren van €0). Komt er later een bij, dan verschijnt hij.
    added_fees: set[str] = set()

    @callback
    def _async_add_fee_sensors() -> None:
        tariff_now = evaluate(coordinator.data)
        new_entities: list[SensorEntity] = []
        if tariff_now.start_fee > 0 and "start" not in added_fees:
            added_fees.add("start")
            new_entities.append(RoadStartFeeSensor(coordinator))
        if tariff_now.blocking_fee and "blocking" not in added_fees:
            added_fees.add("blocking")
            new_entities.append(RoadBlockingFeeSensor(coordinator))
        if new_entities:
            async_add_entities(new_entities)

    _async_add_fee_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_fee_sensors))


@callback
def _async_clear_old_availability_name(
    hass: HomeAssistant, entry: RoadConfigEntry
) -> None:
    """Haal een achtergebleven "<paal> Beschikbaarheid" naam weg (vanaf v2.6).

    De beschikbaarheid-sensor heeft geen eigen naam meer en heet nu gewoon zoals
    de laadpaal. Staat er nog een met de hand ingestelde naam die alleen de oude
    standaardnaam herhaalt ("Beschikbaarheid" of "<paal> Beschikbaarheid"),
    bijvoorbeeld door de naam-migratie van Home Assistant 2026.11, dan wordt die
    gewist. Echt eigen namen blijven staan.
    """
    registry = er.async_get(hass)
    unique_id = f"road_{entry.data['location_id']}_availability"
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    if entity_id is None:
        return
    reg_entry = registry.async_get(entity_id)
    if reg_entry is None or not reg_entry.name:
        return

    names = {entry.title}
    if reg_entry.device_id and (
        device := dr.async_get(hass).async_get(reg_entry.device_id)
    ):
        names.update(n for n in (device.name, device.name_by_user) if n)
    old_defaults = {"beschikbaarheid"} | {
        f"{name} beschikbaarheid".casefold() for name in names
    }
    if " ".join(reg_entry.name.split()).casefold() in old_defaults:
        registry.async_update_entity(entity_id, name=None)


class RoadBaseEntity(RoadEntity, SensorEntity):
    """Basisklasse voor Road sensoren."""


class RoadTariffEntity(RoadBaseEntity):
    """Tariefsensor: elke minuut opnieuw uitrekenen (dag/nacht, datums)."""

    async def async_added_to_hass(self) -> None:
        """Ook zonder nieuwe Road.io data elke minuut bijwerken."""
        await super().async_added_to_hass()

        @callback
        def _tick(_now: datetime) -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_track_time_interval(self.hass, _tick, timedelta(minutes=1))
        )


class RoadLocationPriceSensor(RoadTariffEntity):
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
        """Prijs per kWh incl. btw die nu geldt voor een nieuwe sessie."""
        return evaluate(self.coordinator.data).energy

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Starttarief en blokkeertarief, ook voor de kaart en de melding."""
        tariff_now = evaluate(self.coordinator.data)
        fee = tariff_now.blocking_fee
        return {
            "starttarief": tariff_now.start_fee,
            "blokkeertarief": fee.text if fee else None,
            "verschilt_per_socket": tariffs_differ(self.coordinator.data),
        }


class RoadStartFeeSensor(RoadTariffEntity):
    """Vast bedrag per laadsessie (incl. btw)."""

    _attr_name = "Starttarief"
    _attr_translation_key = "start_fee"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_icon = "mdi:cash-plus"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: RoadDataUpdateCoordinator) -> None:
        """Initialiseer de sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"road_{self.location_id}_start_fee"

    @property
    def native_value(self) -> float:
        """Starttarief voor een sessie die nu start (0 = geen)."""
        return evaluate(self.coordinator.data).start_fee


class RoadBlockingFeeSensor(RoadBaseEntity):
    """Prijs per uur die na een gratis periode gaat tellen."""

    _attr_name = "Blokkeertarief"
    _attr_translation_key = "blocking_fee"
    _attr_native_unit_of_measurement = "EUR/h"
    _attr_icon = "mdi:timer-alert-outline"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: RoadDataUpdateCoordinator) -> None:
        """Initialiseer de sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"road_{self.location_id}_blocking_fee"

    @property
    def native_value(self) -> float | None:
        """Prijs per uur zodra het tarief gaat tellen (0 = geen meer)."""
        fee = evaluate(self.coordinator.data).blocking_fee
        return fee.per_hour if fee else 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Wanneer en hoe het tarief telt."""
        fee = evaluate(self.coordinator.data).blocking_fee
        if fee is None:
            return {"omschrijving": "Geen blokkeertarief"}
        return {
            "omschrijving": fee.text,
            "gratis_minuten": fee.free_minutes,
            "betaald_tot_minuten": fee.until_minutes,
            "tijden": fee.window,
            "dagen": list(fee.days) if fee.days else None,
            "tijdens_laden_per_uur": fee.charging_per_hour,
            "na_laden_per_uur": fee.parking_per_hour,
        }


class RoadAvailabilitySensor(RoadBaseEntity):
    """Samenvattende sensor voor de beschikbaarheid van de hele paal."""

    # Geen eigen naam: dit is de hoofdsensor van de laadpaal en heet dus gewoon
    # zoals de paal ("Eksterweg"). Sinds Home Assistant 2026.11 zet HA de
    # apparaatnaam als context áchter de entiteitnaam; "Beschikbaarheid
    # Eksterweg" werd in Android Auto afgekapt tot "Beschikbaarh...".
    _attr_name = None
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


class RoadFreeSocketsSensor(RoadBaseEntity):
    """Aantal vrije sockets; HA bewaart hiervan uurgemiddelden (statistiek)."""

    _attr_name = "Vrije sockets"
    _attr_translation_key = "free_sockets"
    _attr_icon = "mdi:ev-plug-type2"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: RoadDataUpdateCoordinator) -> None:
        """Initialiseer de sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"road_{self.location_id}_free_sockets"

    @property
    def native_value(self) -> int:
        """Aantal sockets met status AVAILABLE."""
        return free_count(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        """Totaal aantal sockets, voor de kaart."""
        return {"totale_plekken": len(self.evses)}


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
