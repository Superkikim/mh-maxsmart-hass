"""Platform for switch integration."""
import logging
from homeassistant.components.switch import SwitchEntity
from maxsmart import MaxSmartDevice

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    devices = config_entry.data
    entities = []

    for device_id, device_data in devices.items():
        try:
            ip_address = device_data["device_ip"]
            device_name = device_data["device_name"]
            master_port_id = device_data["ports"]["master"]["port_id"]

            maxsmart_device = MaxSmartDevice(ip_address)

            switch_entity = MaxSmartSwitchEntity(
                maxsmart_device, device_name, master_port_id
            )
            entities.append(switch_entity)
        except Exception as e:
            _LOGGER.error("Failed to setup device %s: %s", device_name, e)

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
