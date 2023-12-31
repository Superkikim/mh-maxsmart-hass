"""Platform for switch integration."""
import logging
from homeassistant.components.switch import SwitchEntity
from .coordinator import MaxSmartCoordinator
from maxsmart import MaxSmartDevice
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    _LOGGER.debug("async setup entry for device: %s", config_entry.entry_id)

    device_data = config_entry.data
    device_unique_id = device_data['device_unique_id']
    device_ip = device_data['device_ip']
    device_name = device_data['device_name']
    device_ports = device_data['ports']
    device_version = device_data['sw_version']
    device_model = 'MaxSmart Smart Plug' if len(device_ports['individual_ports']) == 1 else 'MaxSmart Power Station'

    coordinator = MaxSmartCoordinator(hass, device_ip)

    # Start the coordinator
    await coordinator.async_refresh()

    # Create the MaxSmartDevice instance for this device
    maxsmart_device = MaxSmartDevice(device_ip)

    # Create an entity for the master port
    master_port = device_ports['master']
    master_entity = HaMaxSmartPortEntity(coordinator, maxsmart_device, device_unique_id, device_name, 0, master_port['port_name'], device_version, device_model)

    
    # Create an entity for each individual port
    port_entities = [
        HaMaxSmartPortEntity(coordinator, maxsmart_device, device_unique_id, device_name, port['port_id'], port['port_name'], device_version, device_model)
        for port in device_ports['individual_ports']
    ]

    # Add all entities (master + individual ports)
#    async_add_entities(port_entities)
    async_add_entities([master_entity] + port_entities)

class HaMaxSmartPortEntity(SwitchEntity):
    def __init__(self, coordinator, maxsmart_device, device_unique_id, device_name, port_id, port_name, device_version, device_model):
        self._coordinator = coordinator  # Store the coordinator
        self._maxsmart_device = maxsmart_device
        self._device_unique_id = device_unique_id
        self._device_name = device_name
        self._port_id = port_id
        self._port_unique_id = f"{device_unique_id}_{port_id}"
        self._port_name = f"{device_name} {port_name}"
        self._device_version = device_version
        self._device_model = device_model
        self._is_on = None
        self._attr_device_info = self.device_info
        self._attr_unique_id = self.unique_id

#    async def async_added_to_hass(self):
#        """Run when entity about to be added to hass."""
#        await self.hass.async_add_executor_job(self.update)

    @property
    def device_info(self):
        """Return the device info."""
        return {
            "identifiers": {
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self._device_unique_id)
            },
            "name": f"Maxsmart {self._device_name}",
            "manufacturer": "Max Hauri",
            "model": self._device_model,
            "sw_version": self._device_version,
        }
   
    @property
    def name(self):
        return self._port_name

    @property
    def unique_id(self):
        return f"{self._device_unique_id}_{self._port_id}"

    async def async_turn_on(self, **kwargs):
        await self.hass.async_add_executor_job(self._maxsmart_device.turn_on, self._port_id)
        await self.async_update()
        if not self._is_on:
            _LOGGER.error('Failed to turn on device. Update still shows it as off.')

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_executor_job(self._maxsmart_device.turn_off, self._port_id)
        await self.async_update()
        if self._is_on:
            _LOGGER.error('Failed to turn off device. Update still shows it as on.')


    async def async_update(self):
        await self._coordinator.async_refresh()  # Wait for the refresh to complete
        coordinator_data = self._coordinator.data
        switch_list = coordinator_data['switch']
        _LOGGER.debug("Switch_list is %s", switch_list)
        if self._port_id == 0:
            self._is_on = any(state == 1 for state in switch_list)
        else:
            self._is_on = switch_list[self._port_id - 1] == 1
        _LOGGER.debug("port state is %s", switch_list[self._port_id - 1])



    @property
    def is_on(self):
        return self._is_on