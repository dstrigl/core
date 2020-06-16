"""Support for controlling GPIO pins of a Raspberry Pi."""
import logging

from gpiozero import LED, Button
from gpiozero.pins.pigpio import PiGPIOFactory

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

DOMAIN = "remote_rpi_gpio"


def setup(hass, config):
    """Set up the Raspberry Pi Remote GPIO component."""
    return True


def setup_output(address, port, invert_logic):
    """Set up a GPIO as output."""
    return LED(port, active_high=not invert_logic, pin_factory=PiGPIOFactory(address))


def setup_input(address, port, pull_mode, bouncetime):
    """Set up a GPIO as input."""
    if pull_mode == CONF_PULL_MODE_UP:
        pull_gpio_up = True
    elif pull_mode == CONF_PULL_MODE_DOWN:
        pull_gpio_up = False
    else:  # for CONF_PULL_MODE_OFF
        pull_gpio_up = None
    return Button(
        port,
        pull_up=pull_gpio_up,
        active_state=True if pull_mode in CONF_PULL_MODE_OFF else None,
        bounce_time=bouncetime,
        pin_factory=PiGPIOFactory(address),
    )


def write_output(switch, value):
    """Write a value to a GPIO."""
    if value == 1:
        switch.on()
    elif value == 0:
        switch.off()


def read_input(button):
    """Read a value from a GPIO."""
    return button.is_pressed
