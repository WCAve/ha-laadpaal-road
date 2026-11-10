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

from .api import RoadApiClient, RoadConnectionError, RoadLocationNotFoundError
from .const import (
    CONF_DISARM_AFTER_NOTIFY,
    CONF_EXPIRE_HOURS,
    CONF_LOCATION_ID,
    CONF_MIN_FREE_MINUTES,
    CONF_NAME,
    CONF_NOTIFY_TARGETS,
    CONF_NOTIFY_WHEN_TAKEN,
    CONF_PERSON,
    DEFAULT_NAME,
    DEFAULT_OPTIONS,
    DOMAIN,
    TARGET_PERSISTENT,
)

_LOGGER = logging.getLogger(__name__)


def _options_from_other_entries(
    hass: HomeAssistant, exclude_entry_id: str | None = None
) -> dict[str, Any]:
    """Meldingsinstellingen van de laatst ingestelde andere laadpaal."""
    for entry in reversed(hass.config_entries.async_entries(DOMAIN)):
        if entry.entry_id != exclude_entry_id and entry.options:
            return dict(entry.options)
    return {}


class RoadConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handelt de UI setup af in Home Assistant."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RoadOptionsFlow:
        """Meldingsinstellingen via de Configureren knop."""
        return RoadOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Vraag om een naam en Location ID en controleer die bij de API."""
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
                return self.async_create_entry(
                    title=name,
                    data={CONF_NAME: name, CONF_LOCATION_ID: location_id},
                    # Neem de meldingsinstellingen van je vorige laadpaal over.
                    options=_options_from_other_entries(self.hass),
                )

        return self.async_show_form(
            step_id="user",
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
