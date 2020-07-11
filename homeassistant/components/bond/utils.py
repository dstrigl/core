"""Reusable utilities for the Bond component."""

from typing import List

from bond import Bond

from homeassistant.core import HomeAssistant


class BondDevice:
    """Helper device class to hold ID and attributes together."""

    def __init__(self, device_id: str, attrs: dict):
        """Create a helper device from ID and attributes returned by API."""
        self.device_id = device_id
        self._attrs = attrs

    @property
    def name(self) -> str:
        """Get the name of this device."""
        return self._attrs["name"]

    @property
    def type(self) -> str:
        """Get the type of this device."""
        return self._attrs["type"]

    def supports_command(self, command: str) -> bool:
        """Return True if this device supports specified command."""
        actions: List[str] = self._attrs["actions"]
        return command in actions


def get_bond_devices(hass: HomeAssistant, bond: Bond) -> List[BondDevice]:
    """Fetch all available devices using Bond API."""
    device_ids = bond.getDeviceIds()
    devices = [
        BondDevice(device_id, bond.getDevice(device_id)) for device_id in device_ids
    ]
    return devices
