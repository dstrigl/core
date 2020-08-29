"""Support for Modbus covers."""
import logging
from typing import Optional

import voluptuous as vol

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    DEVICE_CLASS_BLIND,
    PLATFORM_SCHEMA,
    SUPPORT_CLOSE,
    SUPPORT_OPEN,
    SUPPORT_SET_POSITION,
    SUPPORT_SET_TILT_POSITION,
    SUPPORT_STOP,
    CoverEntity,
)
from homeassistant.const import CONF_NAME, CONF_SLAVE
from homeassistant.helpers import config_validation as cv
from pymodbus.constants import Endian
from pymodbus.exceptions import ConnectionException, ModbusException
from pymodbus.payload import BinaryPayloadBuilder, BinaryPayloadDecoder
from pymodbus.pdu import ExceptionResponse

from .const import CONF_HUB, DEFAULT_HUB, MODBUS_DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_CURRENT_STATUS_ADDR = "current_status_addr"
CONF_REQUEST_STATUS_ADDR = "request_status_addr"

# OSCAT status values (BYTE)
STATUS_OPENING = 121
STATUS_CLOSING = 122
STATUS_STANDBY = 131
STATUS_OPEN = 134
STATUS_CLOSE = 135
STATUS_SET = 136

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_HUB, default=DEFAULT_HUB): cv.string,
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_SLAVE): cv.positive_int,
        vol.Required(CONF_CURRENT_STATUS_ADDR): cv.positive_int,
        vol.Required(CONF_REQUEST_STATUS_ADDR): cv.positive_int,
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Read configuration and create Modbus devices."""
    hub_name = config[CONF_HUB]
    hub = hass.data[MODBUS_DOMAIN][hub_name]
    name = config[CONF_NAME]
    slave = config[CONF_SLAVE]
    current_status_addr = config[CONF_CURRENT_STATUS_ADDR]
    request_status_addr = config[CONF_REQUEST_STATUS_ADDR]

    add_entities(
        [ModbusCover(hub, name, slave, current_status_addr, request_status_addr)]
    )


def scale_to_255(value):
    """Scale the input value from 0-100 to 0-255."""
    return max(0, min(255, ((value * 255.0) / 100.0)))


def scale_to_100(value):
    """Scale the input value from 0-255 to 0-100."""
    return max(0, min(100, ((value * 100.0) / 255.0)))


class ModbusCover(CoverEntity):
    """Representation of a Modbus cover."""

    def __init__(self, hub, name, slave, current_status_addr, request_status_addr):
        """Initialize the cover."""
        self._hub = hub
        self._name = name
        self._slave = int(slave) if slave else None
        self._current_status_addr = int(current_status_addr)
        self._request_status_addr = int(request_status_addr)
        self._status = None
        self._cover_position = None
        self._cover_tilt_position = None
        self._available = True

    @property
    def name(self):
        """Return the name of the cover."""
        return self._name

    @property
    def device_class(self) -> Optional[str]:
        """Return the class of this device."""
        return DEVICE_CLASS_BLIND

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def supported_features(self):
        """Flag supported features."""
        supported_features = (
            SUPPORT_OPEN
            | SUPPORT_CLOSE
            | SUPPORT_SET_POSITION
            | SUPPORT_SET_TILT_POSITION
            | SUPPORT_STOP
        )
        return supported_features

    @property
    def current_cover_position(self):
        """Return current position of the cover.

        None is unknown, 0 is closed, 100 is fully open.
        """
        return self._cover_position

    @property
    def current_cover_tilt_position(self):
        """Return current position of the cover tilt.

        None is unknown, 0 is closed, 100 is fully open.
        """
        return self._cover_tilt_position

    @property
    def is_opening(self):
        """Return if the cover is opening or not."""
        if self._status is None:
            return None
        return self._status == STATUS_OPENING

    @property
    def is_closing(self):
        """Return if the cover is closing or not."""
        if self._status is None:
            return None
        return self._status == STATUS_CLOSING

    @property
    def is_closed(self):
        """Return if the cover is closed or not."""
        if self._cover_position is None or self._cover_tilt_position is None:
            return None
        return self._cover_position == 0 and self._cover_tilt_position < 2

    def _write_registers(self, address, values) -> None:
        """Write holding registers using the Modbus hub slave."""
        try:
            self._hub.write_registers(self._slave, address, values)
        except ConnectionException:
            self._available = False
            return
        self._available = True

    def open_cover(self, **kwargs):
        """Open the cover."""
        builder = BinaryPayloadBuilder()
        builder.add_8bit_uint(STATUS_OPEN)
        self._write_registers(self._request_status_addr, builder.to_registers())

    def close_cover(self, **kwargs):
        """Close cover."""
        builder = BinaryPayloadBuilder()
        builder.add_8bit_uint(STATUS_CLOSE)
        self._write_registers(self._request_status_addr, builder.to_registers())

    def stop_cover(self, **kwargs):
        """Stop the cover."""
        builder = BinaryPayloadBuilder()
        builder.add_8bit_uint(STATUS_STANDBY)
        self._write_registers(self._request_status_addr, builder.to_registers())

    def _set_position_and_angle(self, position, angle) -> None:
        position = int(scale_to_255(position))
        angle = int(scale_to_255(angle))
        builder = BinaryPayloadBuilder(byteorder=Endian.Little)
        builder.add_16bit_uint(STATUS_SET)
        builder.add_16bit_uint(position)
        builder.add_16bit_uint(angle)
        self._write_registers(self._request_status_addr, builder.to_registers())

    def set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        if ATTR_POSITION in kwargs:
            self._set_position_and_angle(
                kwargs[ATTR_POSITION], self._cover_tilt_position
            )

    def set_cover_tilt_position(self, **kwargs):
        """Move the cover tilt to a specific position."""
        if ATTR_TILT_POSITION in kwargs:
            self._set_position_and_angle(
                self._cover_position, kwargs[ATTR_TILT_POSITION]
            )

    def update(self):
        """Update the state of the cover."""
        try:
            result = self._hub.read_holding_registers(
                self._slave, self._current_status_addr, 3
            )
        except ConnectionException:
            self._available = False
            return
        if isinstance(result, (ModbusException, ExceptionResponse)):
            self._available = False
            return
        dec = BinaryPayloadDecoder.fromRegisters(
            result.registers, byteorder=Endian.Little
        )
        self._status = dec.decode_16bit_uint() & 0xFF
        self._cover_position = scale_to_100(dec.decode_16bit_uint() & 0xFF)
        self._cover_tilt_position = scale_to_100(dec.decode_16bit_uint() & 0xFF)
        self._available = True
