"""Support for RFXtrx covers."""
import logging

import RFXtrx as rfxtrxmod
import voluptuous as vol

from homeassistant.components.cover import PLATFORM_SCHEMA, CoverEntity
from homeassistant.const import ATTR_STATE, CONF_DEVICES, CONF_NAME, STATE_OPEN
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.restore_state import RestoreEntity

from . import (
    ATTR_FIRE_EVENT,
    CONF_AUTOMATIC_ADD,
    CONF_FIRE_EVENT,
    CONF_SIGNAL_REPETITIONS,
    DEFAULT_SIGNAL_REPETITIONS,
    SIGNAL_EVENT,
    RfxtrxDevice,
    fire_command_event,
    get_device_id,
    get_rfx_object,
)
from .const import COMMAND_OFF_LIST, COMMAND_ON_LIST

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_DEVICES, default={}): {
            cv.string: vol.Schema(
                {
                    vol.Required(CONF_NAME): cv.string,
                    vol.Optional(CONF_FIRE_EVENT, default=False): cv.boolean,
                }
            )
        },
        vol.Optional(CONF_AUTOMATIC_ADD, default=False): cv.boolean,
        vol.Optional(
            CONF_SIGNAL_REPETITIONS, default=DEFAULT_SIGNAL_REPETITIONS
        ): vol.Coerce(int),
    }
)

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the RFXtrx cover."""
    device_ids = set()

    entities = []
    for packet_id, entity_info in config[CONF_DEVICES].items():
        event = get_rfx_object(packet_id)
        if event is None:
            _LOGGER.error("Invalid device: %s", packet_id)
            continue

        device_id = get_device_id(event.device)
        if device_id in device_ids:
            continue
        device_ids.add(device_id)

        datas = {ATTR_STATE: None, ATTR_FIRE_EVENT: entity_info[CONF_FIRE_EVENT]}
        entity = RfxtrxCover(
            entity_info[CONF_NAME], event.device, datas, config[CONF_SIGNAL_REPETITIONS]
        )
        entities.append(entity)

    add_entities(entities)

    def cover_update(event):
        """Handle cover updates from the RFXtrx gateway."""
        if (
            not isinstance(event.device, rfxtrxmod.LightingDevice)
            or event.device.known_to_be_dimmable
            or not event.device.known_to_be_rollershutter
        ):
            return

        device_id = get_device_id(event.device)
        if device_id in device_ids:
            return
        device_ids.add(device_id)

        _LOGGER.info(
            "Added cover (Device ID: %s Class: %s Sub: %s)",
            event.device.id_string.lower(),
            event.device.__class__.__name__,
            event.device.subtype,
        )

        pkt_id = "".join(f"{x:02x}" for x in event.data)
        datas = {ATTR_STATE: False, ATTR_FIRE_EVENT: False}
        entity = RfxtrxCover(
            pkt_id, event.device, datas, DEFAULT_SIGNAL_REPETITIONS, event=event
        )
        add_entities([entity])

    # Subscribe to main RFXtrx events
    if config[CONF_AUTOMATIC_ADD]:
        hass.helpers.dispatcher.dispatcher_connect(SIGNAL_EVENT, cover_update)


class RfxtrxCover(RfxtrxDevice, CoverEntity, RestoreEntity):
    """Representation of a RFXtrx cover."""

    async def async_added_to_hass(self):
        """Restore RFXtrx cover device state (OPEN/CLOSE)."""
        await super().async_added_to_hass()

        old_state = await self.async_get_last_state()
        if old_state is not None:
            self._state = old_state.state == STATE_OPEN

        self.async_on_remove(
            self.hass.helpers.dispatcher.async_dispatcher_connect(
                SIGNAL_EVENT, self._handle_event
            )
        )

    @property
    def should_poll(self):
        """Return the polling state. No polling available in RFXtrx cover."""
        return False

    @property
    def is_closed(self):
        """Return if the cover is closed."""
        return not self._state

    def open_cover(self, **kwargs):
        """Move the cover up."""
        self._send_command("roll_up")

    def close_cover(self, **kwargs):
        """Move the cover down."""
        self._send_command("roll_down")

    def stop_cover(self, **kwargs):
        """Stop the cover."""
        self._send_command("stop_roll")

    def _apply_event(self, event):
        """Apply command from rfxtrx."""
        if event.values["Command"] in COMMAND_ON_LIST:
            self._state = True
        elif event.values["Command"] in COMMAND_OFF_LIST:
            self._state = False

    def _handle_event(self, event):
        """Check if event applies to me and update."""
        if event.device.id_string != self._device.id_string:
            return

        self._apply_event(event)

        self.schedule_update_ha_state()
        if self.should_fire_event:
            fire_command_event(self.hass, self.entity_id, event.values["Command"])
