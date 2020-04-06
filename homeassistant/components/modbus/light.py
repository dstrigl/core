"""Support for Modbus lights."""
import logging

import voluptuous as vol

from homeassistant.components.light import (
    PLATFORM_SCHEMA,
    ATTR_BRIGHTNESS,
    SUPPORT_BRIGHTNESS,
    Light,
)
from homeassistant.const import CONF_NAME, CONF_SLAVE, STATE_ON
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.restore_state import RestoreEntity
from pymodbus.payload import BinaryPayloadBuilder
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

from . import CONF_HUB, DEFAULT_HUB, DOMAIN as MODBUS_DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_STATE_COIL = "state_coil"
CONF_BRIGHTNESS_REGISTER = "brightness_register"

DEFAULT_BRIGHTNESS = 255
BYTEORDER = Endian.Little

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_HUB, default=DEFAULT_HUB): cv.string,
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_SLAVE): cv.positive_int,
        vol.Required(CONF_STATE_COIL): cv.positive_int,
        vol.Optional(CONF_BRIGHTNESS_REGISTER): cv.positive_int,
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Read configuration and create Modbus devices."""
    hub_name = config.get(CONF_HUB)
    hub = hass.data[MODBUS_DOMAIN][hub_name]
    name = config.get(CONF_NAME)
    slave = config.get(CONF_SLAVE)
    state_coil = config.get(CONF_STATE_COIL)
    brightness_register = config.get(CONF_BRIGHTNESS_REGISTER)

    add_entities([ModbusLight(
        hub, name, slave, state_coil, brightness_register
        )]
    )


class ModbusLight(Light, RestoreEntity):
    """Representation of a Modbus light."""

    def __init__(self, hub, name, slave, state_coil, brightness_register):
        """Initialize the light."""
        self._hub = hub
        self._name = name
        self._slave = int(slave) if slave else None
        self._state_coil = int(state_coil)
        self._brightness_register = brightness_register
        if self._brightness_register is not None:
            self._brightness_register = int(self._brightness_register)
        self._is_on = None
        self._brightness = None

    async def async_added_to_hass(self):
        """Handle entity about to be added to hass event."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state:
            self._is_on = last_state.state == STATE_ON
            if self.supported_features & SUPPORT_BRIGHTNESS:
                self._brightness = last_state.attributes.get(
                    "brightness", DEFAULT_BRIGHTNESS
                )

    @property
    def name(self):
        """Return the name of the light."""
        return self._name

    @property
    def is_on(self):
        """Return true if the light is on."""
        return self._is_on

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        return self._brightness

    @property
    def supported_features(self):
        """Flag supported features."""
        supported_features = 0
        if self._brightness_register is not None:
            supported_features |= SUPPORT_BRIGHTNESS
        return supported_features

    def turn_on(self, **kwargs):
        """Turn on the light."""
        if self.supported_features & SUPPORT_BRIGHTNESS \
                and ATTR_BRIGHTNESS in kwargs:
            brightness = int(kwargs[ATTR_BRIGHTNESS])
            brightness = max(0, min(255, brightness))
            builder = BinaryPayloadBuilder(byteorder=BYTEORDER)
            builder.add_16bit_uint(brightness)
            self._hub.write_registers(
                self._slave, self._brightness_register, builder.to_registers()
            )
        self._hub.write_coil(self._slave, self._state_coil, True)

    def turn_off(self, **kwargs):
        """Turn off the light."""
        self._hub.write_coil(self._slave, self._state_coil, False)

    def update(self):
        """Update the state of the light."""
        if self.supported_features & SUPPORT_BRIGHTNESS:
            result = self._hub.read_holding_registers(
                self._slave, self._brightness_register, 1
            )
            try:
                dec = BinaryPayloadDecoder.fromRegisters(
                    result.registers, byteorder=BYTEORDER
                )
                self._brightness = dec.decode_16bit_uint()
            except AttributeError:
                _LOGGER.error(
                    "No response from hub %s, slave %s, register %s"
                    " (brightness)",
                    self._hub.name,
                    self._slave,
                    self._brightness_register,
                )
        result = self._hub.read_coils(
            self._slave, self._state_coil, 1
        )
        try:
            self._is_on = bool(result.bits[0])
        except AttributeError:
            _LOGGER.error(
                "No response from hub %s, slave %s, coil %s"
                " (state)",
                self._hub.name,
                self._slave,
                self._state_coil,
            )
