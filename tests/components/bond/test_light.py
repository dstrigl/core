"""Tests for the Bond light device."""
from datetime import timedelta
import logging

from bond import Actions, DeviceTypes

from homeassistant import core
from homeassistant.components.light import ATTR_BRIGHTNESS, DOMAIN as LIGHT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.util import utcnow

from .common import (
    patch_bond_device_state,
    patch_bond_set_flame,
    patch_bond_turn_off,
    patch_bond_turn_on,
    patch_turn_light_off,
    patch_turn_light_on,
    setup_platform,
)

from tests.common import async_fire_time_changed

_LOGGER = logging.getLogger(__name__)


def ceiling_fan(name: str):
    """Create a ceiling fan (that has built-in light) with given name."""
    return {
        "name": name,
        "type": DeviceTypes.CEILING_FAN,
        "actions": [Actions.TOGGLE_LIGHT],
    }


def fireplace(name: str):
    """Create a fireplace with given name."""
    return {"name": name, "type": DeviceTypes.FIREPLACE}


async def test_entity_registry(hass: core.HomeAssistant):
    """Tests that the devices are registered in the entity registry."""
    await setup_platform(hass, LIGHT_DOMAIN, ceiling_fan("name-1"))

    registry: EntityRegistry = await hass.helpers.entity_registry.async_get_registry()
    assert [key for key in registry.entities] == ["light.name_1"]


async def test_turn_on_light(hass: core.HomeAssistant):
    """Tests that turn on command delegates to API."""
    await setup_platform(hass, LIGHT_DOMAIN, ceiling_fan("name-1"))

    with patch_turn_light_on() as mock_turn_light_on, patch_bond_device_state():
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "light.name_1"},
            blocking=True,
        )
        await hass.async_block_till_done()
        mock_turn_light_on.assert_called_once()


async def test_turn_off_light(hass: core.HomeAssistant):
    """Tests that turn off command delegates to API."""
    await setup_platform(hass, LIGHT_DOMAIN, ceiling_fan("name-1"))

    with patch_turn_light_off() as mock_turn_light_off, patch_bond_device_state():
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: "light.name_1"},
            blocking=True,
        )
        await hass.async_block_till_done()
        mock_turn_light_off.assert_called_once()


async def test_update_reports_light_is_on(hass: core.HomeAssistant):
    """Tests that update command sets correct state when Bond API reports the light is on."""
    await setup_platform(hass, LIGHT_DOMAIN, ceiling_fan("name-1"))

    with patch_bond_device_state(return_value={"light": 1}):
        async_fire_time_changed(hass, utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done()

    assert hass.states.get("light.name_1").state == "on"


async def test_update_reports_light_is_off(hass: core.HomeAssistant):
    """Tests that update command sets correct state when Bond API reports the light is off."""
    await setup_platform(hass, LIGHT_DOMAIN, ceiling_fan("name-1"))

    with patch_bond_device_state(return_value={"light": 0}):
        async_fire_time_changed(hass, utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done()

    assert hass.states.get("light.name_1").state == "off"


async def test_turn_on_fireplace(hass: core.HomeAssistant):
    """Tests that turn on command delegates to API."""
    await setup_platform(
        hass, LIGHT_DOMAIN, fireplace("name-1"), bond_device_id="test-device-id"
    )

    with patch_bond_turn_on() as mock_turn_on, patch_bond_set_flame() as mock_set_flame, patch_bond_device_state():
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: "light.name_1", ATTR_BRIGHTNESS: 128},
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_turn_on.assert_called_once()
    mock_set_flame.assert_called_once_with("test-device-id", 50)


async def test_turn_off_fireplace(hass: core.HomeAssistant):
    """Tests that turn off command delegates to API."""
    await setup_platform(hass, LIGHT_DOMAIN, fireplace("name-1"))

    with patch_bond_turn_off() as mock_turn_off, patch_bond_device_state():
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: "light.name_1"},
            blocking=True,
        )
        await hass.async_block_till_done()
        mock_turn_off.assert_called_once()


async def test_flame_converted_to_brightness(hass: core.HomeAssistant):
    """Tests that reported flame level (0..100) converted to HA brightness (0...255)."""
    await setup_platform(hass, LIGHT_DOMAIN, fireplace("name-1"))

    with patch_bond_device_state(return_value={"power": 1, "flame": 50}):
        async_fire_time_changed(hass, utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done()

    _LOGGER.warning(hass.states.get("light.name_1").attributes)
    assert hass.states.get("light.name_1").attributes[ATTR_BRIGHTNESS] == 128
