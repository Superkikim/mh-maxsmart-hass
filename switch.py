"""Platform for switch integration."""
import logging
from homeassistant.components.switch import SwitchEntity
from maxsmart import MaxSmartDevice
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    _LOGGER.info("async setup entry for device: %s", config_entry.entry_id)

    device_data = config_entry.data
    device_ip = device_data['device_ip']
    device_name = device_data['device_name']
    ports = device_data['ports']

    # Create the MaxSmartDevice instance for this device
    maxsmart_device = MaxSmartDevice(device_ip)

    # Create an entity for the master port
    master_port = ports['master']
    master_entity = MaxSmartSwitchEntity(maxsmart_device, f"{device_name} Master", master_port['port_id'])
    
    # Create an entity for each individual port
    port_entities = [
        MaxSmartSwitchEntity(maxsmart_device, f"{device_name} {port['port_name']}", port['port_id'])
        for port in ports['individual_ports']
    ]

    # Add all entities (master + individual ports)
    async_add_entities([master_entity] + port_entities)



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
        await self.hass.async_add_executor_job(self._maxsmart_device.turn_on, self._master_port_id)
        self._is_on = True
        self.async_write_ha_state()
    except Exception as e:
        _LOGGER.error("Failed to turn on %s: %s", self._device_name, e)

async def async_turn_off(self, **kwargs):
    try:
        await self.hass.async_add_executor_job(self._maxsmart_device.turn_off, self._master_port_id)
        self._is_on = False
        self.async_write_ha_state()
    except Exception as e:
        _LOGGER.error("Failed to turn off %s: %s", self._device_name, e)

    async def async_update(self):
    try:
        port_state = await self.hass.async_add_executor_job(self._maxsmart_device.check_port_state, self._master_port_id)
        self._is_on = port_state == 1
    except Exception as e:
        _LOGGER.error("Failed to update state of %s: %s", self._device_name, e)
