"""Support for Modbus fans."""
import logging
from typing import Optional

from pymodbus.constants import Endian
from pymodbus.exceptions import ConnectionException, ModbusException
from pymodbus.payload import BinaryPayloadBuilder, BinaryPayloadDecoder
from pymodbus.pdu import ExceptionResponse
import voluptuous as vol

from homeassistant.components.fan import (
    ATTR_SPEED,
    PLATFORM_SCHEMA,
    SPEED_HIGH,
    SPEED_LOW,
    SPEED_MEDIUM,
    SUPPORT_SET_SPEED,
    FanEntity,
)
from homeassistant.const import CONF_NAME, CONF_SLAVE, STATE_OFF, STATE_ON
from homeassistant.helpers import config_validation as cv

from .const import CONF_HUB, DEFAULT_HUB, MODBUS_DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_STATE_COIL = "state_coil"
CONF_SPEED_REGISTER = "speed_register"

SPEED_TO_VALUE = {SPEED_LOW: 0, SPEED_MEDIUM: 1, SPEED_HIGH: 2}
VALUE_TO_SPEED = {0: SPEED_LOW, 1: SPEED_MEDIUM, 2: SPEED_HIGH}
BYTEORDER = Endian.Little

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_HUB, default=DEFAULT_HUB): cv.string,
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_SLAVE): cv.positive_int,
        vol.Required(CONF_STATE_COIL): cv.positive_int,
        vol.Optional(CONF_SPEED_REGISTER): cv.positive_int,
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Read configuration and create Modbus devices."""
    hub_name = config[CONF_HUB]
    hub = hass.data[MODBUS_DOMAIN][hub_name]
    name = config[CONF_NAME]
    slave = config[CONF_SLAVE]
    state_coil = config[CONF_STATE_COIL]
    speed_register = config.get(CONF_SPEED_REGISTER)

    add_entities([ModbusFan(hub, name, slave, state_coil, speed_register)])


class ModbusFan(FanEntity):
    """Representation of a Modbus fan."""

    def __init__(self, hub, name, slave, state_coil, speed_register):
        """Initialize the fan."""
        self._hub = hub
        self._name = name
        self._slave = int(slave) if slave else None
        self._state_coil = int(state_coil)
        self._speed_register = speed_register
        if self._speed_register is not None:
            self._speed_register = int(self._speed_register)
        self._state = STATE_OFF
        self._speed = None
        self._available = True

    @property
    def name(self):
        """Return the name of the fan."""
        return self._name

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        supported_features = 0
        if self._speed_register is not None:
            supported_features |= SUPPORT_SET_SPEED
        return supported_features

    @property
    def is_on(self):
        """Return true if the fan is on."""
        return self._state == STATE_ON

    @property
    def speed(self) -> Optional[str]:
        """Return the current speed."""
        return self._speed

    @property
    def speed_list(self) -> list:
        """Get the list of available speeds."""
        return [SPEED_LOW, SPEED_MEDIUM, SPEED_HIGH]

    def _write_coil(self, coil, value):
        """Write coil using the Modbus hub slave."""
        try:
            self._hub.write_coil(self._slave, coil, value)
        except ConnectionException:
            self._available = False
            return
        self._available = True

    def turn_on(self, speed: str = None, **kwargs) -> None:
        """Turn on the fan."""
        if speed is not None:
            self.set_speed(speed)
            if not self._available:
                return
        self._write_coil(self._state_coil, True)

    def turn_off(self, **kwargs):
        """Turn off the fan."""
        self._write_coil(self._state_coil, False)

    def set_speed(self, speed: str) -> None:
        """Set the speed of the fan."""
        if speed in SPEED_TO_VALUE:
            builder = BinaryPayloadBuilder(byteorder=BYTEORDER)
            builder.add_16bit_int(SPEED_TO_VALUE[speed])
            try:
                self._hub.write_registers(
                    self._slave, self._speed_register, builder.to_registers()
                )
            except ConnectionException:
                self._available = False

    def update(self):
        """Update the state of the fan."""
        speed = None
        if self.supported_features & SUPPORT_SET_SPEED:
            try:
                result = self._hub.read_holding_registers(
                    self._slave, self._speed_register, 1
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
            speed = dec.decode_16bit_int()
        try:
            result = self._hub.read_coils(self._slave, self._state_coil, 1)
        except ConnectionException:
            self._available = False
            return
        if isinstance(result, (ModbusException, ExceptionResponse)):
            self._available = False
            return
        self._state = STATE_ON if bool(result.bits[0]) else STATE_OFF
        if speed is not None:
            self._speed = VALUE_TO_SPEED[speed] if speed in VALUE_TO_SPEED else None
        self._available = True
