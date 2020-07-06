"""Support for Modbus lights."""
import logging

from pymodbus.constants import Endian
from pymodbus.exceptions import ConnectionException, ModbusException
from pymodbus.payload import BinaryPayloadBuilder, BinaryPayloadDecoder
from pymodbus.pdu import ExceptionResponse
import voluptuous as vol

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    PLATFORM_SCHEMA,
    SUPPORT_BRIGHTNESS,
    LightEntity,
)
from homeassistant.const import CONF_NAME, CONF_SLAVE
from homeassistant.helpers import config_validation as cv

from .const import CONF_HUB, DEFAULT_HUB, MODBUS_DOMAIN

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
    hub_name = config[CONF_HUB]
    hub = hass.data[MODBUS_DOMAIN][hub_name]
    name = config[CONF_NAME]
    slave = config[CONF_SLAVE]
    state_coil = config[CONF_STATE_COIL]
    brightness_register = config.get(CONF_BRIGHTNESS_REGISTER)

    add_entities([ModbusLight(hub, name, slave, state_coil, brightness_register)])


class ModbusLight(LightEntity):
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
        self._available = True

    @property
    def name(self):
        """Return the name of the light."""
        return self._name

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def supported_features(self):
        """Flag supported features."""
        supported_features = 0
        if self._brightness_register is not None:
            supported_features |= SUPPORT_BRIGHTNESS
        return supported_features

    @property
    def is_on(self):
        """Return true if the light is on."""
        return self._is_on

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        return self._brightness

    def _write_coil(self, coil, value):
        """Write coil using the Modbus hub slave."""
        try:
            self._hub.write_coil(self._slave, coil, value)
        except ConnectionException:
            self._available = False
            return
        self._available = True

    def turn_on(self, **kwargs):
        """Turn on the light."""
        if self.supported_features & SUPPORT_BRIGHTNESS and ATTR_BRIGHTNESS in kwargs:
            brightness = int(kwargs[ATTR_BRIGHTNESS])
            brightness = max(0, min(255, brightness))
            builder = BinaryPayloadBuilder(byteorder=BYTEORDER)
            builder.add_16bit_uint(brightness)
            try:
                self._hub.write_registers(
                    self._slave, self._brightness_register, builder.to_registers()
                )
            except ConnectionException:
                self._available = False
                return
        self._write_coil(self._state_coil, True)

    def turn_off(self, **kwargs):
        """Turn off the light."""
        self._write_coil(self._state_coil, False)

    def update(self):
        """Update the state of the light."""
        brightness = None
        if self.supported_features & SUPPORT_BRIGHTNESS:
            try:
                result = self._hub.read_holding_registers(
                    self._slave, self._brightness_register, 1
                )
            except ConnectionException:
                self._available = False
                return
            if isinstance(result, (ModbusException, ExceptionResponse)):
                self._available = False
                return
            dec = BinaryPayloadDecoder.fromRegisters(
                result.registers, byteorder=BYTEORDER
            )
            brightness = dec.decode_16bit_uint()
        try:
            result = self._hub.read_coils(self._slave, self._state_coil, 1)
        except ConnectionException:
            self._available = False
            return
        if isinstance(result, (ModbusException, ExceptionResponse)):
            self._available = False
            return
        self._is_on = bool(result.bits[0])
        if brightness is not None:
            self._brightness = brightness
        self._available = True
