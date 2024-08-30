"""Platform for switch integration."""
import logging
from homeassistant.components.switch import SwitchEntity
from .coordinator import MaxSmartCoordinator
import maxsmart
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    _LOGGER.debug("Starting async_setup_entry for device: %s", config_entry.entry_id)

    device_data = config_entry.data
    _LOGGER.debug("Device data loaded: %s", device_data)

    device_unique_id = device_data['device_unique_id']
    device_ip = device_data['device_ip']
    device_name = device_data['device_name']
    device_ports = device_data['ports']
    device_version = device_data['sw_version']
    device_model = 'MaxSmart Smart Plug' if len(device_ports['individual_ports']) == 1 else 'MaxSmart Power Station'

    _LOGGER.debug("Device unique ID: %s", device_unique_id)
    _LOGGER.debug("Device IP: %s", device_ip)
    _LOGGER.debug("Device Name: %s", device_name)
    _LOGGER.debug("Device Ports: %s", device_ports)
    _LOGGER.debug("Device Version: %s", device_version)
    _LOGGER.debug("Device Model: %s", device_model)

    coordinator = MaxSmartCoordinator(hass, device_ip)
    _LOGGER.debug("Coordinator initialized for IP: %s", device_ip)

    # Start the coordinator
    await coordinator.async_refresh()
    _LOGGER.debug("Coordinator refresh completed")

    # Create the MaxSmartDevice instance for this device
    maxsmart_device = maxsmart.device.MaxSmartDevice(device_ip)
    _LOGGER.debug("MaxSmartDevice instance created for IP: %s", device_ip)

    # Create an entity for the master port
    master_port = device_ports['master']
    _LOGGER.debug("Creating master entity for port: %s", master_port)
    master_entity = HaMaxSmartPortEntity(coordinator, maxsmart_device, device_unique_id, device_name, 0, master_port['port_name'], device_version, device_model)
    _LOGGER.debug("Master entity created: %s", master_entity)

    # Create an entity for each individual port
    _LOGGER.debug("Creating entities for individual ports")
    port_entities = [
        HaMaxSmartPortEntity(coordinator, maxsmart_device, device_unique_id, device_name, port['port_id'], port['port_name'], device_version, device_model)
        for port in device_ports['individual_ports']
    ]
    _LOGGER.debug("Port entities created: %s", port_entities)

    # Add all entities (master + individual ports)
    _LOGGER.debug("Adding entities to Home Assistant")
    async_add_entities([master_entity] + port_entities)
    _LOGGER.debug("Entities added to Home Assistant")
    _LOGGER.debug("Updating states")
    await coordinator.async_refresh()

class HaMaxSmartPortEntity(SwitchEntity):
    def __init__(self, coordinator, maxsmart_device, device_unique_id, device_name, port_id, port_name, device_version, device_model):
        _LOGGER.debug("Initializing HaMaxSmartPortEntity for port %s", port_id)
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
        _LOGGER.debug("HaMaxSmartPortEntity initialized: %s", self._port_unique_id)

    @property
    def device_info(self):
        """Return the device info."""
        info = {
            "identifiers": {
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self._device_unique_id)
            },
            "name": f"Maxsmart {self._device_name}",
            "manufacturer": "Max Hauri",
            "model": self._device_model,
            "sw_version": self._device_version,
        }
        _LOGGER.debug("Device info for %s: %s", self._port_unique_id, info)
        return info
   
    @property
    def name(self):
        _LOGGER.debug("Returning name for port %s: %s", self._port_id, self._port_name)
        return self._port_name

    @property
    def unique_id(self):
        _LOGGER.debug("Returning unique_id for port %s: %s", self._port_id, self._port_unique_id)
        return self._port_unique_id

    async def async_turn_on(self, **kwargs):
        _LOGGER.debug("Turning on port %s", self._port_id)
        await self.hass.async_add_executor_job(self._maxsmart_device.turn_on, self._port_id)
        await self.async_update()
        if not self._is_on:
            _LOGGER.error('Failed to turn on device. Update still shows it as off for port %s', self._port_id)

    async def async_turn_off(self, **kwargs):
        _LOGGER.debug("Turning off port %s", self._port_id)
        await self.hass.async_add_executor_job(self._maxsmart_device.turn_off, self._port_id)
        await self.async_update()
        if self._is_on:
            _LOGGER.error('Failed to turn off device. Update still shows it as on for port %s', self._port_id)

    async def async_update(self):
        """Update the switch state using the latest data from the coordinator."""
        _LOGGER.debug("Updating switch state for port %s", self._port_id)
        await self._coordinator.async_refresh()
        switch_list = self._coordinator.data.get('switch', [])
        
        if self._port_id == 0:
            self._is_on = any(state == 1 for state in switch_list)
        else:
            self._is_on = switch_list[self._port_id - 1] == 1
        
        _LOGGER.debug("Switch state for port %s is now %s", self._port_id, self._is_on)
    

    @property
    def is_on(self):
        _LOGGER.debug("Returning is_on state for port %s: %s", self._port_id, self._is_on)
        return self._is_on
