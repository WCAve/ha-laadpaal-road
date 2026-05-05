"""Config flow voor Road.io."""
import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_LOCATION_ID, CONF_NAME

class EfluxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handelt de UI setup af in Home Assistant."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Behandel de input van de gebruiker."""
        if user_input is not None:
            # Maak de integratie aan met de gekozen naam als titel
            return self.async_create_entry(
                title=user_input[CONF_NAME], 
                data=user_input
            )

        # Toon het formulier met velden voor naam en locatie ID
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default="Mijn Laadpaal"): str,
                vol.Required(CONF_LOCATION_ID): str,
            })
        )