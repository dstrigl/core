"""Support for Risco alarms."""
import logging

from homeassistant.components.alarm_control_panel import AlarmControlPanelEntity
from homeassistant.components.alarm_control_panel.const import (
    SUPPORT_ALARM_ARM_AWAY,
    SUPPORT_ALARM_ARM_HOME,
)
from homeassistant.const import (
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_ARMED_HOME,
    STATE_ALARM_ARMING,
    STATE_ALARM_DISARMED,
    STATE_ALARM_TRIGGERED,
)

from .const import DATA_COORDINATOR, DOMAIN
from .entity import RiscoEntity

_LOGGER = logging.getLogger(__name__)

SUPPORTED_STATES = [
    STATE_ALARM_DISARMED,
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_ARMED_HOME,
    STATE_ALARM_TRIGGERED,
]


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Risco alarm control panel."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    entities = [
        RiscoAlarm(coordinator, partition_id)
        for partition_id in coordinator.data.partitions
    ]

    async_add_entities(entities, False)


class RiscoAlarm(AlarmControlPanelEntity, RiscoEntity):
    """Representation of a Risco partition."""

    def __init__(self, coordinator, partition_id):
        """Init the partition."""
        super().__init__(coordinator)
        self._partition_id = partition_id
        self._partition = self._coordinator.data.partitions[self._partition_id]

    def _get_data_from_coordinator(self):
        self._partition = self._coordinator.data.partitions[self._partition_id]

    @property
    def device_info(self):
        """Return device info for this device."""
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "manufacturer": "Risco",
        }

    @property
    def name(self):
        """Return the name of the partition."""
        return f"Risco {self._risco.site_name} Partition {self._partition_id}"

    @property
    def unique_id(self):
        """Return a unique id for that partition."""
        return f"{self._risco.site_uuid}_{self._partition_id}"

    @property
    def state(self):
        """Return the state of the device."""
        if self._partition.triggered:
            return STATE_ALARM_TRIGGERED
        if self._partition.arming:
            return STATE_ALARM_ARMING
        if self._partition.armed:
            return STATE_ALARM_ARMED_AWAY
        if self._partition.partially_armed:
            return STATE_ALARM_ARMED_HOME
        if self._partition.disarmed:
            return STATE_ALARM_DISARMED

        return None

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_ALARM_ARM_HOME | SUPPORT_ALARM_ARM_AWAY

    @property
    def code_arm_required(self):
        """Whether the code is required for arm actions."""
        return False

    async def async_alarm_disarm(self, code=None):
        """Send disarm command."""
        await self._call_alarm_method("disarm")

    async def async_alarm_arm_home(self, code=None):
        """Send arm home command."""
        await self._call_alarm_method("partial_arm")

    async def async_alarm_arm_away(self, code=None):
        """Send arm away command."""
        await self._call_alarm_method("arm")

    async def _call_alarm_method(self, method, code=None):
        alarm = await getattr(self._risco, method)(self._partition_id)
        self._partition = alarm.partitions[self._partition_id]
        self.async_write_ha_state()
