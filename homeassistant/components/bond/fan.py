"""Support for Bond fans."""
from typing import Any, Callable, List, Optional

from bond import Bond, DeviceTypes

from homeassistant.components.fan import (
    SPEED_HIGH,
    SPEED_LOW,
    SPEED_MEDIUM,
    SPEED_OFF,
    SUPPORT_SET_SPEED,
    FanEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .entity import BondEntity
from .utils import BondDevice, get_bond_devices


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable[[List[Entity], bool], None],
) -> None:
    """Set up Bond fan devices."""
    bond: Bond = hass.data[DOMAIN][entry.entry_id]

    devices = await hass.async_add_executor_job(get_bond_devices, hass, bond)

    fans = [
        BondFan(bond, device)
        for device in devices
        if device.type == DeviceTypes.CEILING_FAN
    ]

    async_add_entities(fans, True)


class BondFan(BondEntity, FanEntity):
    """Representation of a Bond fan."""

    def __init__(self, bond: Bond, device: BondDevice):
        """Create HA entity representing Bond fan."""
        super().__init__(bond, device)

        self._power: Optional[bool] = None
        self._speed: Optional[int] = None

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        features = 0
        if self._device.supports_command("SetSpeed"):
            features |= SUPPORT_SET_SPEED
        return features

    @property
    def speed(self) -> Optional[str]:
        """Return the current speed."""
        if self._power is None:
            return None
        if self._power == 0:
            return SPEED_OFF

        return self.speed_list[self._speed] if self._speed is not None else None

    @property
    def speed_list(self) -> list:
        """Get the list of available speeds."""
        return [SPEED_OFF, SPEED_LOW, SPEED_MEDIUM, SPEED_HIGH]

    def update(self):
        """Fetch assumed state of the fan from the hub using API."""
        state: dict = self._bond.getDeviceState(self._device.device_id)
        self._power = state.get("power")
        self._speed = state.get("speed")

    def set_speed(self, speed: str) -> None:
        """Set the desired speed for the fan."""
        speed_index = self.speed_list.index(speed)
        self._bond.setSpeed(self._device.device_id, speed=speed_index)

    def turn_on(self, speed: Optional[str] = None, **kwargs) -> None:
        """Turn on the fan."""
        if speed is not None:
            self.set_speed(speed)
        self._bond.turnOn(self._device.device_id)

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the fan off."""
        self._bond.turnOff(self._device.device_id)
