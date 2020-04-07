"""Support for Heliotherm heat pump thermostat via HtREST."""
import json
import asyncio
import logging
from typing import Optional, List

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant.components.climate import PLATFORM_SCHEMA, ClimateDevice
from homeassistant.components.climate.const import (
    HVAC_MODE_AUTO,
    SUPPORT_TARGET_TEMPERATURE,
)
from homeassistant.const import (
    EVENT_HOMEASSISTANT_START,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    ATTR_TEMPERATURE,
    CONF_NAME,
    CONF_RESOURCE,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_TIMEOUT,
    CONF_VERIFY_SSL,
    TEMP_CELSIUS,
    PRECISION_HALVES,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_track_state_change

_LOGGER = logging.getLogger(__name__)

CONF_SENSOR = "target_sensor"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"
CONF_PRECISION = "precision"
CONF_STEP = "temp_step"

DEFAULT_TIMEOUT = 10
DEFAULT_VERIFY_SSL = True
DEFAULT_MIN_TEMP = 10
DEFAULT_MAX_TEMP = 25
DEFAULT_PRECISION = 1  # TODO
DEFAULT_STEP = 0.5

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_SENSOR): cv.entity_id,
        vol.Required(CONF_RESOURCE): cv.url,
        vol.Inclusive(CONF_USERNAME, "authentication"): cv.string,
        vol.Inclusive(CONF_PASSWORD, "authentication"): cv.string,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean,
        vol.Optional(CONF_MIN_TEMP, default=DEFAULT_MIN_TEMP): cv.positive_int,
        vol.Optional(CONF_MAX_TEMP, default=DEFAULT_MAX_TEMP): cv.positive_int,
        # vol.Optional(CONF_PRECISION, default=DEFAULT_PRECISION): cv.positive_int,  # TODO
        vol.Optional(CONF_PRECISION, default=DEFAULT_PRECISION): vol.In(
            [PRECISION_TENTHS, PRECISION_HALVES, PRECISION_WHOLE]
        ),
        vol.Optional(CONF_STEP, default=DEFAULT_STEP): vol.Coerce(float),
    }
)


async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Heliotherm heat pump thermostat device."""
    name = config[CONF_NAME]
    sensor_entity_id = config.get(CONF_SENSOR)
    resource = config[CONF_RESOURCE]
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    timeout = config[CONF_TIMEOUT]
    verify_ssl = config[CONF_VERIFY_SSL]
    min_temp = config[CONF_MIN_TEMP]
    max_temp = config[CONF_MAX_TEMP]
    precision = config[CONF_PRECISION]
    temp_step = config[CONF_STEP]

    auth = None
    if username:
        auth = aiohttp.BasicAuth(username, password=password)

    add_entities(
        [
            HtRestThermostat(
                name,
                sensor_entity_id,
                resource,
                auth,
                timeout,
                verify_ssl,
                min_temp,
                max_temp,
                precision,
                temp_step,
            )
        ],
        True,
    )


class HtRestThermostat(ClimateDevice):
    """Representation of a Heliotherm heat pump thermostat."""

    def __init__(
        self,
        name,
        sensor_entity_id,
        resource,
        auth,
        timeout,
        verify_ssl,
        min_temp,
        max_temp,
        precision,
        temp_step,
    ):
        """Initialize the unit."""
        self._name = name
        self._sensor_entity_id = sensor_entity_id
        self._resource = resource
        self._auth = auth
        self._timeout = timeout
        self._verify_ssl = verify_ssl
        self._min_temp = min_temp
        self._max_temp = max_temp
        self._precision = precision
        self._temp_step = temp_step
        self._target_temp = None
        self._current_temp = None
        self._available = True

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        # Add listener
        if self._sensor_entity_id:
            async_track_state_change(
                self.hass, self._sensor_entity_id, self._async_sensor_changed
            )

        @callback
        def _async_startup(event) -> None:
            """Init on startup."""
            if self._sensor_entity_id:
                sensor_state = self.hass.states.get(self._sensor_entity_id)
                if sensor_state and sensor_state.state not in (
                    STATE_UNAVAILABLE,
                    STATE_UNKNOWN,
                ):
                    self._async_update_temp(sensor_state)

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, _async_startup)

    async def _async_sensor_changed(self, entity_id, old_state, new_state) -> None:
        """Handle temperature changes."""
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        self._async_update_temp(new_state)
        self.async_write_ha_state()  # TODO?

    @callback
    def _async_update_temp(self, state) -> None:
        """Update thermostat with latest state from sensor."""
        try:
            self._current_temp = float(state.state)
        except ValueError as ex:
            _LOGGER.error("Unable to update from sensor: %s", ex)

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self._name

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        return SUPPORT_TARGET_TEMPERATURE

    @property
    def hvac_mode(self) -> str:
        """Return the current HVAC mode."""
        return HVAC_MODE_AUTO

    @property
    def hvac_modes(self) -> List[str]:
        """Return the possible HVAC modes."""
        return [HVAC_MODE_AUTO]

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        return self._current_temp

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the target temperature."""
        return self._target_temp

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return self._min_temp

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return self._max_temp

    @property
    def precision(self) -> float:
        """Return the precision of the device."""
        return self._precision

    @property
    def target_temperature_step(self) -> Optional[float]:
        """Return the supported step of target temperature."""
        return self._temp_step

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        assert isinstance(temperature, float)
        self._target_temp = temperature
        try:
            websession = async_get_clientsession(self.hass, self._verify_ssl)
            with async_timeout.timeout(self._timeout):
                req = await getattr(websession, "put")(
                    self._resource,  # TODO --> "/api/v1/param/HKR%20Soll_Raum"
                    auth=self._auth,
                    data=bytes(json.dumps({"value": temperature}), "utf-8"),
                    headers={
                        "accept": "application/json",
                        "Content-Type": "application/json",
                    },
                )
            if req.status == 200:
                text = await req.text()
                self._target_temp = float(json.loads(text)["value"])
                self._available = True
            else:
                _LOGGER.error(
                    "Can't set target temperature %s. Is resource/endpoint offline?",
                    self._resource,
                )
        except asyncio.TimeoutError:
            _LOGGER.exception(
                "Timed out while setting target temperature %s", self._resource
            )
        except aiohttp.ClientError as err:
            _LOGGER.exception(
                "Error while setting target temperature %s: %s", self._resource, err
            )

    async def async_update(self) -> None:
        """Update target temperature."""
        try:
            websession = async_get_clientsession(self.hass, self._verify_ssl)
            with async_timeout.timeout(self._timeout):
                req = await getattr(websession, "put")(
                    self._resource,  # TODO --> "/api/v1/param/HKR%20Soll_Raum"
                    auth=self._auth,
                    headers={"accept": "application/json"},
                )
                text = await req.text()
            self._target_temp = float(json.loads(text)["value"])
            self._available = True
        except asyncio.TimeoutError:
            _LOGGER.exception(
                "Timed out while fetching target temperature %s", self._resource
            )
            self._available = False
        except aiohttp.ClientError as err:
            _LOGGER.exception(
                "Error while fetching target temperature %s: %s", self._resource, err
            )
            self._available = False
