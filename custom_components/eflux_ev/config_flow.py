import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_LOCATION_ID

class EfluxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow voor Road.io."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # Hier kunnen we later nog validatie toevoegen
            return self.async_create_entry(title=f"Lader {user_input[CONF_LOCATION_ID]}", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_LOCATION_ID): str,
            }),
            errors=errors,
        )