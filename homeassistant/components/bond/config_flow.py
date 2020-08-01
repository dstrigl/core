"""Config flow for Bond integration."""
import logging

from aiohttp import ClientConnectionError, ClientResponseError
from bond_api import Bond
import voluptuous as vol

from homeassistant import config_entries, exceptions
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_HOST

from .const import DOMAIN  # pylint:disable=unused-import

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {vol.Required(CONF_HOST): str, vol.Required(CONF_ACCESS_TOKEN): str}
)


async def validate_input(data) -> str:
    """Validate the user input allows us to connect."""

    try:
        bond = Bond(data[CONF_HOST], data[CONF_ACCESS_TOKEN])
        version = await bond.version()
        # call to non-version API is needed to validate authentication
        await bond.devices()
    except ClientConnectionError:
        raise CannotConnect
    except ClientResponseError as error:
        if error.status == 401:
            raise InvalidAuth
        raise

    # Return unique ID from the hub to be stored in the config entry.
    return version["bondid"]


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bond."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                bond_id = await validate_input(user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(bond_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=bond_id, data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""
