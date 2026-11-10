"""Config flow voor Road.io."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RoadApiClient, RoadConnectionError, RoadLocationNotFoundError
from .const import CONF_LOCATION_ID, CONF_NAME, DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


class RoadConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handelt de UI setup af in Home Assistant."""

    VERSION = 1

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
