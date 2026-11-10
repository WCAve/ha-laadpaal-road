"""Config flow en opties (Configureren) voor Road.io."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    RoadApiClient,
    RoadApiError,
    RoadConnectionError,
    RoadLocationNotFoundError,
)
from .const import (
    CONF_ADDRESS,
    CONF_DISARM_AFTER_NOTIFY,
    CONF_EXPIRE_HOURS,
    CONF_LOCATION,
    CONF_LOCATION_ID,
    CONF_MIN_FREE_MINUTES,
    CONF_NAME,
    CONF_NOTIFY_TARGETS,
    CONF_NOTIFY_WHEN_TAKEN,
    CONF_PERSON,
    DEFAULT_NAME,
    DEFAULT_OPTIONS,
    DOMAIN,
    SEARCH_MAX_RESULTS,
    SEARCH_RADIUS_DEFAULT,
    SEARCH_RADIUS_MAX,
    SEARCH_RADIUS_MIN,
    TARGET_PERSISTENT,
)
from .data import evses, free_count
from .geocode import GeocodeError, async_geocode

_LOGGER = logging.getLogger(__name__)


def _options_from_other_entries(
    hass: HomeAssistant, exclude_entry_id: str | None = None
) -> dict[str, Any]:
    """Meldingsinstellingen van de laatst ingestelde andere laadpaal."""
    for entry in reversed(hass.config_entries.async_entries(DOMAIN)):
        if entry.entry_id != exclude_entry_id and entry.options:
            return dict(entry.options)
    return {}


def _address(location: dict[str, Any]) -> str:
    """'Straat 12, Plaats', of een terugval op het ID."""
    parts = [str(location.get(key) or "").strip() for key in ("address", "city")]
    text = ", ".join(part for part in parts if part)
    return text or f"Laadpaal {str(location.get('id', ''))[:8]}"


def _format_distance(meters: float) -> str:
    if meters >= 1000:
        return f"{meters / 1000:.1f} km".replace(".", ",")
    return f"{round(meters)} m"


def _label(location: dict[str, Any]) -> str:
    """Regel in de keuzelijst: adres · aanbieder · vrij · afstand."""
    parts = [_address(location)]
    operator = (location.get("operator") or {}).get("name")
    if operator:
        parts.append(str(operator))
    total = len(evses(location))
    if total:
        parts.append(f"{free_count(location)}/{total} vrij")
    parts.append(_format_distance(location["distance"]))
    return " · ".join(parts)


class RoadConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handelt de UI setup af in Home Assistant."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialiseer de flow."""
        self._found: dict[str, dict[str, Any]] = {}
        self._geocoded_query: str | None = None
        self._place: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RoadOptionsFlow:
        """Meldingsinstellingen via de Configureren knop."""
        return RoadOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Kies: zoeken op de kaart of zelf een Location ID invullen."""
        return self.async_show_menu(step_id="user", menu_options=["search", "manual"])

    async def async_step_search(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Kies een plek: typ een adres en/of zet de pin op de kaart.

        Met een (nieuw) adres verplaatst Verzenden alleen de kaart, zodat je
        kunt zien waar hij terechtkwam. Nog een keer Verzenden zoekt dan de
        laadpalen rond de pin.
        """
        errors: dict[str, str] = {}
        address = ""
        location = {
            "latitude": self.hass.config.latitude,
            "longitude": self.hass.config.longitude,
            "radius": SEARCH_RADIUS_DEFAULT,
        }

        if user_input is not None:
            location = dict(user_input[CONF_LOCATION])
            address = (user_input.get(CONF_ADDRESS) or "").strip()

            if address and address != self._geocoded_query:
                try:
                    place = await async_geocode(
                        async_get_clientsession(self.hass),
                        address,
                        self.hass.config.language or "nl",
                    )
                except GeocodeError:
                    errors["base"] = "geocode_failed"
                except Exception:
                    _LOGGER.exception("Onverwachte fout bij adres opzoeken")
                    errors["base"] = "unknown"
                else:
                    if place is None:
                        errors[CONF_ADDRESS] = "address_not_found"
                    else:
                        # Onthoud de zoekterm: nog eens Verzenden = zoeken.
                        self._geocoded_query = address
                        self._place = place.name
                        location["latitude"] = place.latitude
                        location["longitude"] = place.longitude
                return self._async_show_search_form(location, address, errors)

            return await self._async_search_chargers(location, address)

        return self._async_show_search_form(location, address, errors)

    async def async_step_search_found(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Zelfde formulier, maar met de gevonden plek in de uitleg."""
        return await self.async_step_search(user_input)

    async def _async_search_chargers(
        self, location: dict[str, Any], address: str
    ) -> ConfigFlowResult:
        """Zoek laadpalen rond de pin en ga door naar de keuzelijst."""
        errors: dict[str, str] = {}
        radius = float(location.get("radius") or SEARCH_RADIUS_DEFAULT)
        radius = min(max(radius, SEARCH_RADIUS_MIN), SEARCH_RADIUS_MAX)

        api = RoadApiClient(async_get_clientsession(self.hass))
        try:
            results = await api.async_search(
                location["latitude"], location["longitude"], radius
            )
        except RoadApiError:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Onverwachte fout bij zoeken naar laadpalen")
            errors["base"] = "unknown"
        else:
            configured = self._async_current_ids()
            new = [loc for loc in results if loc["id"] not in configured]
            if not results:
                errors["base"] = "no_chargers"
            elif not new:
                errors["base"] = "all_added"
            else:
                self._found = {loc["id"]: loc for loc in new[:SEARCH_MAX_RESULTS]}
                return await self.async_step_pick()

        return self._async_show_search_form(location, address, errors)

    @callback
    def _async_show_search_form(
        self, location: dict[str, Any], address: str, errors: dict[str, str]
    ) -> ConfigFlowResult:
        schema = vol.Schema(
            {
                vol.Optional(CONF_ADDRESS): selector.TextSelector(),
                vol.Required(CONF_LOCATION): selector.LocationSelector(
                    selector.LocationSelectorConfig(radius=True, icon="mdi:ev-station")
                ),
            }
        )
        # Na een gevonden adres: ander uitleg-tekstje met de gevonden plek.
        found = bool(address) and address == self._geocoded_query
        return self.async_show_form(
            step_id="search_found" if found else "search",
            data_schema=self.add_suggested_values_to_schema(
                schema, {CONF_ADDRESS: address, CONF_LOCATION: location}
            ),
            errors=errors,
            description_placeholders={
                "max_radius": str(SEARCH_RADIUS_MAX),
                "place": self._place or "",
            },
        )

    async def async_step_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Kies een van de gevonden laadpalen."""
        if user_input is not None:
            location = self._found[user_input[CONF_LOCATION_ID]]
            name = (user_input.get(CONF_NAME) or "").strip() or _address(location)
            await self.async_set_unique_id(location["id"])
            self._abort_if_unique_id_configured()
            return self._async_create(name, location["id"])

        options = [
            selector.SelectOptionDict(value=location_id, label=_label(location))
            for location_id, location in self._found.items()
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_LOCATION_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=(
                            selector.SelectSelectorMode.LIST
                            if len(options) <= 8
                            else selector.SelectSelectorMode.DROPDOWN
                        ),
                    )
                ),
                vol.Optional(CONF_NAME): str,
            }
        )
        return self.async_show_form(
            step_id="pick",
            data_schema=schema,
            description_placeholders={"count": str(len(options))},
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Vul zelf een naam en Location ID in; die wordt gecontroleerd."""
        errors: dict[str, str] = {}

        if user_input is not None:
            location_id = user_input[CONF_LOCATION_ID].strip()
            name = user_input[CONF_NAME].strip() or DEFAULT_NAME

            await self.async_set_unique_id(location_id)
            self._abort_if_unique_id_configured()

            api = RoadApiClient(async_get_clientsession(self.hass))
            try:
                await api.async_get_location(location_id)
            except RoadLocationNotFoundError:
                errors[CONF_LOCATION_ID] = "invalid_location"
            except RoadConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Onverwachte fout bij controleren van Location ID")
                errors["base"] = "unknown"
            else:
                return self._async_create(name, location_id)

        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                        vol.Required(CONF_LOCATION_ID): str,
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    @callback
    def _async_create(self, name: str, location_id: str) -> ConfigFlowResult:
        return self.async_create_entry(
            title=name,
            data={CONF_NAME: name, CONF_LOCATION_ID: location_id},
            # Neem de meldingsinstellingen van je vorige laadpaal over.
            options=_options_from_other_entries(self.hass),
        )


class RoadOptionsFlow(OptionsFlow):
    """Meldingsinstellingen voor de Laadwens van één laadpaal."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Toon en bewaar de meldingsinstellingen."""
        if user_input is not None:
            if not user_input.get(CONF_PERSON):
                user_input.pop(CONF_PERSON, None)
            return self.async_create_entry(data=user_input)

        current = {
            **DEFAULT_OPTIONS,
            **(
                self.config_entry.options
                or _options_from_other_entries(
                    self.hass, exclude_entry_id=self.config_entry.entry_id
                )
            ),
        }
        schema = vol.Schema(
            {
                vol.Optional(CONF_NOTIFY_TARGETS): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self._target_options(current[CONF_NOTIFY_TARGETS]),
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(CONF_DISARM_AFTER_NOTIFY): selector.BooleanSelector(),
                vol.Required(CONF_NOTIFY_WHEN_TAKEN): selector.BooleanSelector(),
                vol.Optional(CONF_PERSON): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="person")
                ),
                vol.Required(CONF_EXPIRE_HOURS): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=24,
                        step=0.5,
                        unit_of_measurement="uur",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(CONF_MIN_FREE_MINUTES): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=30,
                        step=1,
                        unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, current),
        )

    def _target_options(self, selected: list[str]) -> list[selector.SelectOptionDict]:
        """Alle notify services, met leesbare namen. Telefoons eerst."""
        services = set(self.hass.services.async_services_for_domain("notify"))
        services -= {"send_message", TARGET_PERSISTENT}

        def label(service: str) -> str:
            if service.startswith("mobile_app_"):
                device = service.removeprefix("mobile_app_").replace("_", " ")
                return f"Telefoon: {device}"
            return f"notify.{service}"

        options = [
            selector.SelectOptionDict(value=service, label=label(service))
            for service in sorted(
                services, key=lambda s: (not s.startswith("mobile_app_"), s)
            )
        ]
        options.append(
            selector.SelectOptionDict(
                value=TARGET_PERSISTENT, label="Meldingen in Home Assistant zelf"
            )
        )
        # Eerder gekozen doelen die (nu) niet bestaan niet stilletjes laten vallen.
        known = {option["value"] for option in options}
        options.extend(
            selector.SelectOptionDict(
                value=service, label=f"{label(service)} (niet gevonden)"
            )
            for service in selected
            if service not in known
        )
        return options
