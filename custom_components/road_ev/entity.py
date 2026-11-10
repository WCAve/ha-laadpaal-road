"""Gedeelde basis voor alle entiteiten van deze integratie."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RoadDataUpdateCoordinator
from .data import evses


class RoadEntity(CoordinatorEntity[RoadDataUpdateCoordinator]):
    """Koppelt een entiteit aan het apparaat van één laadlocatie."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RoadDataUpdateCoordinator) -> None:
        """Initialiseer de entiteit."""
        super().__init__(coordinator)
        self.location_id = coordinator.location_id
        operator = ((coordinator.data or {}).get("operator") or {}).get("name")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.location_id)},
            name=coordinator.config_entry.title,
            # De exploitant van de paal (bv. Vattenfall, Allego).
            manufacturer=operator or None,
        )

    @property
    def evses(self) -> list[dict[str, Any]]:
        """Sockets van de laatst opgehaalde data."""
        return evses(self.coordinator.data)
