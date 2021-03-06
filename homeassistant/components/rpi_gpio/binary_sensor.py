"""Support for binary sensor using RPi GPIO."""
import voluptuous as vol

from homeassistant.components import rpi_gpio
from homeassistant.components.binary_sensor import PLATFORM_SCHEMA, BinarySensorEntity
from homeassistant.const import DEVICE_DEFAULT_NAME
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.reload import setup_reload_service

from . import (
    CONF_BOUNCETIME,
    CONF_INVERT_LOGIC,
    CONF_PULL_MODE,
    DEFAULT_BOUNCETIME,
    DEFAULT_INVERT_LOGIC,
    DEFAULT_PULL_MODE,
    DOMAIN,
    PLATFORMS,
    PULL_MODES,
)

CONF_PORTS = "ports"

_SENSORS_SCHEMA = vol.Schema({cv.positive_int: cv.string})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_PORTS): _SENSORS_SCHEMA,
        vol.Optional(CONF_BOUNCETIME, default=DEFAULT_BOUNCETIME): cv.positive_int,
        vol.Optional(CONF_INVERT_LOGIC, default=DEFAULT_INVERT_LOGIC): cv.boolean,
        vol.Optional(CONF_PULL_MODE, default=DEFAULT_PULL_MODE): vol.In(PULL_MODES),
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Raspberry PI GPIO devices."""

    setup_reload_service(hass, DOMAIN, PLATFORMS)

    pull_mode = config.get(CONF_PULL_MODE)
    bouncetime = config.get(CONF_BOUNCETIME)
    invert_logic = config.get(CONF_INVERT_LOGIC)

    binary_sensors = []
    ports = config["ports"]
    for port_num, port_name in ports.items():
        binary_sensors.append(
            RPiGPIOBinarySensor(
                port_name, port_num, pull_mode, bouncetime, invert_logic
            )
        )
    add_entities(binary_sensors, True)


class RPiGPIOBinarySensor(BinarySensorEntity):
    """Represent a binary sensor that uses Raspberry Pi GPIO."""

    def __init__(self, name, port, pull_mode, bouncetime, invert_logic):
        """Initialize the RPi binary sensor."""
        self._name = name or DEVICE_DEFAULT_NAME
        self._port = port
        self._pull_mode = pull_mode
        self._bouncetime = bouncetime
        self._invert_logic = invert_logic
        self._state = False
        rpi_gpio.setup_input(self._port, self._pull_mode)

    async def async_added_to_hass(self):
        """Handle entity which will be added."""

        def read_gpio(port):
            """Read state from GPIO."""
            self._state = rpi_gpio.read_input(self._port)
            self.schedule_update_ha_state()

        rpi_gpio.edge_detect(self._port, read_gpio, self._bouncetime)

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def is_on(self):
        """Return the state of the entity."""
        return self._state != self._invert_logic

    def update(self):
        """Update the GPIO state."""
        self._state = rpi_gpio.read_input(self._port)
