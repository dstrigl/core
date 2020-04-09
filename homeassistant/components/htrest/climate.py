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
    CURRENT_HVAC_OFF,
    CURRENT_HVAC_IDLE,
    CURRENT_HVAC_HEAT,
)
from homeassistant.const import (
    EVENT_HOMEASSISTANT_START,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    ATTR_TEMPERATURE,
    CONF_NAME,
    CONF_HOST,
    CONF_PORT,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_TIMEOUT,
    TEMP_CELSIUS,
    PRECISION_TENTHS,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_track_state_change

_LOGGER = logging.getLogger(__name__)

CONF_SENSOR = "target_sensor"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"
CONF_STEP = "temp_step"

DEFAULT_PORT = 8777
DEFAULT_TIMEOUT = 10
DEFAULT_MIN_TEMP = 10
DEFAULT_MAX_TEMP = 25
DEFAULT_STEP = 0.5

URL_PARAM = "api/v1/param/"
PARAM_HKR_SOLL_RAUM = "HKR Soll_Raum"
PARAM_STOERUNG = "Stoerung"
PARAM_HAUPTSCHALTER = "Hauptschalter"
PARAM_HEIZKREISPUMPE = "Heizkreispumpe"
PARAM_WARMWASSERVORRANG = "Warmwasservorrang"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_SENSOR): cv.entity_id,
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Inclusive(CONF_USERNAME, "authentication"): cv.string,
        vol.Inclusive(CONF_PASSWORD, "authentication"): cv.string,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
        vol.Optional(CONF_MIN_TEMP, default=DEFAULT_MIN_TEMP): cv.positive_int,
        vol.Optional(CONF_MAX_TEMP, default=DEFAULT_MAX_TEMP): cv.positive_int,
        vol.Optional(CONF_STEP, default=DEFAULT_STEP): vol.Coerce(float),
    }
)


async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Heliotherm heat pump thermostat device."""
    name = config[CONF_NAME]
    sensor_entity_id = config.get(CONF_SENSOR)
    host = config[CONF_HOST]
    port = config[CONF_PORT]
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    timeout = config[CONF_TIMEOUT]
    min_temp = config[CONF_MIN_TEMP]
    max_temp = config[CONF_MAX_TEMP]
    temp_step = config[CONF_STEP]

    auth = None
    if username:
        auth = aiohttp.BasicAuth(username, password=password)

    add_entities(
        [
            HtRestThermostat(
                name,
                sensor_entity_id,
                host,
                port,
                auth,
                timeout,
                min_temp,
                max_temp,
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
        host,
        port,
        auth,
        timeout,
        min_temp,
        max_temp,
        temp_step,
    ):
        """Initialize the unit."""
        self._name = name
        self._sensor_entity_id = sensor_entity_id
        self._resource = "http://{}:{}/{}".format(host, port, URL_PARAM)
        self._auth = auth
        self._timeout = timeout
        self._min_temp = min_temp
        self._max_temp = max_temp
        self._temp_step = temp_step
        self._target_temp = None
        self._current_temp = None
        self._current_hvac_action = None
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
        self.async_write_ha_state()

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

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode."""
        assert hvac_mode == HVAC_MODE_AUTO

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation."""
        return self._current_hvac_action

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
        return PRECISION_TENTHS

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
        resource = self._resource + PARAM_HKR_SOLL_RAUM
        try:
            websession = async_get_clientsession(self.hass)
            with async_timeout.timeout(self._timeout):
                req = await websession.put(
                    resource,
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
                self.async_write_ha_state()
            else:
                _LOGGER.error(
                    "Can't set target temperature (%s). Is resource/endpoint offline?",
                    resource,
                )
        except asyncio.TimeoutError:
            _LOGGER.exception(
                "Timed out while setting target temperature (%s)", resource
            )
        except aiohttp.ClientError as err:
            _LOGGER.exception(
                "Error while setting target temperature (%s): %s", resource, err
            )

    async def async_update(self) -> None:
        """Update target temperature."""
        try:
            websession = async_get_clientsession(self.hass)
            with async_timeout.timeout(self._timeout):
                params = (
                    PARAM_HKR_SOLL_RAUM,
                    PARAM_STOERUNG,
                    PARAM_HAUPTSCHALTER,
                    PARAM_HEIZKREISPUMPE,
                    PARAM_WARMWASSERVORRANG,
                )
                req = await websession.get(
                    self._resource,
                    auth=self._auth,
                    headers={"accept": "application/json"},
                    params={param: "" for param in params},
                )
                text = await req.text()
            try:
                values = json.loads(text)
                self._target_temp = float(values[PARAM_HKR_SOLL_RAUM])
                if values[PARAM_STOERUNG] or not values[PARAM_HAUPTSCHALTER]:
                    self._current_hvac_action = CURRENT_HVAC_OFF
                elif (
                    values[PARAM_HEIZKREISPUMPE] and not values[PARAM_WARMWASSERVORRANG]
                ):
                    self._current_hvac_action = CURRENT_HVAC_HEAT
                else:
                    self._current_hvac_action = CURRENT_HVAC_IDLE
                self._available = True
            except Exception:
                _LOGGER.exception("Invalid response from %s: %s", self._resource, text)
                self._available = False
        except asyncio.TimeoutError:
            _LOGGER.exception("Timed out while fetching data from %s", self._resource)
            self._available = False
        except aiohttp.ClientError as err:
            _LOGGER.exception(
                "Error while fetching data from %s: %s", self._resource, err
            )
            self._available = False
