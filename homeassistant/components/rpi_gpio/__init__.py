"""Support for controlling GPIO pins of a Raspberry Pi."""
import logging

from RPi import GPIO  # pylint: disable=import-error

from homeassistant.const import EVENT_HOMEASSISTANT_START, EVENT_HOMEASSISTANT_STOP

_LOGGER = logging.getLogger(__name__)

CONF_BOUNCETIME = "bouncetime"
CONF_INVERT_LOGIC = "invert_logic"
CONF_PULL_MODE = "pull_mode"
CONF_PULL_MODE_UP = "UP"
CONF_PULL_MODE_DOWN = "DOWN"
CONF_PULL_MODE_OFF = ["OFF", False]

DEFAULT_BOUNCETIME = 50
DEFAULT_INVERT_LOGIC = False
DEFAULT_PULL_MODE = CONF_PULL_MODE_UP
PULL_MODES = [CONF_PULL_MODE_UP, CONF_PULL_MODE_DOWN] + CONF_PULL_MODE_OFF

DOMAIN = "rpi_gpio"
PLATFORMS = ["binary_sensor", "cover", "switch"]


def setup(hass, config):
    """Set up the Raspberry PI GPIO component."""

    def cleanup_gpio(event):
        """Stuff to do before stopping."""
        GPIO.cleanup()

    def prepare_gpio(event):
        """Stuff to do when Home Assistant starts."""
        hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, cleanup_gpio)

    hass.bus.listen_once(EVENT_HOMEASSISTANT_START, prepare_gpio)
    GPIO.setmode(GPIO.BCM)
    return True


def setup_output(port):
    """Set up a GPIO as output."""
    GPIO.setup(port, GPIO.OUT)


def setup_input(port, pull_mode):
    """Set up a GPIO as input."""
    if pull_mode == CONF_PULL_MODE_UP:
        pull_up_down = GPIO.PUD_UP
    elif pull_mode == CONF_PULL_MODE_DOWN:
        pull_up_down = GPIO.PUD_DOWN
    else:  # for CONF_PULL_MODE_OFF
        pull_up_down = GPIO.PUD_OFF
    GPIO.setup(port, GPIO.IN, pull_up_down)


def write_output(port, value):
    """Write a value to a GPIO."""
    GPIO.output(port, value)


def read_input(port):
    """Read a value from a GPIO."""
    return GPIO.input(port)


def edge_detect(port, event_callback, bounce):
    """Add detection for RISING and FALLING events."""
    GPIO.add_event_detect(port, GPIO.BOTH, callback=event_callback, bouncetime=bounce)
