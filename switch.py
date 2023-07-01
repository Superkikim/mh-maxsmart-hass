"""Platform for switch integration."""
import logging
from homeassistant.components.switch import SwitchEntity
from maxsmart import MaxSmartDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    _LOGGER.info("async setup entry for device: %s", config_entry.entry_id)
    device_entry_id = config_entry.entry_id  # Retrieve the entry ID for the current device

    # Retrieve all entities associated with the current device entry
    entities = [entity for entity in hass.data[DOMAIN]["entities"] if entity.entry_id == device_entry_id]
    _LOGGER.info("entities are : %s", entities)

    async_add_entities(entities)



class MaxSmartSwitchEntity(SwitchEntity):
    def __init__(self, maxsmart_device, device_name, master_port_id):
        self._maxsmart_device = maxsmart_device
        self._device_name = device_name
        self._master_port_id = master_port_id
        self._is_on = None

    @property
    def should_poll(self):
        return True

    @property
    def name(self):
        return self._device_name

    @property
    def is_on(self):
        return self._is_on

    async def async_turn_on(self, **kwargs):
        try:
            await self._maxsmart_device.turn_on(self._master_port_id)
            self._is_on = True
            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error("Failed to turn on %s: %s", self._device_name, e)

    async def async_turn_off(self, **kwargs):
        try:
            await self._maxsmart_device.turn_off(self._master_port_id)
            self._is_on = False
            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error("Failed to turn off %s: %s", self._device_name, e)

    async def async_update(self):
        try:
            port_state = await self._maxsmart_device.check_port_state(self._master_port_id)
            self._is_on = port_state == 1
        except Exception as e:
            _LOGGER.error("Failed to update state of %s: %s", self._device_name, e)
