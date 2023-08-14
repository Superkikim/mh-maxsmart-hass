"""Platform for sensor integration."""
import logging
from datetime import timedelta
from homeassistant.const import DEVICE_CLASS_POWER
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from .const import DOMAIN
from .coordinator import MaxSmartCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    _LOGGER.debug("async setup entry for power sensors: %s", config_entry.entry_id)

    device_data = config_entry.data
    device_unique_id = device_data['device_unique_id']
    device_ip = device_data['device_ip']
    device_name = device_data['device_name']
    device_ports = device_data['ports']
    device_version = device_data['sw_version']
    device_model = 'Maxsmart Smart Plug' if len(device_ports['individual_ports']) == 1 else 'Maxsmart Power Station'

    coordinator = MaxSmartCoordinator(hass, device_ip)

    # Start the coordinator
    await coordinator.async_refresh()

    # Create power sensor entities for each individual port
    power_sensor_entities = [
        HaMaxSmartPowerSensor(coordinator, device_unique_id, device_name, port['port_id'], port['port_name'], device_version, device_model)
        for port in device_ports['individual_ports']
    ]

    # Add all power sensor entities
    async_add_entities(power_sensor_entities)

class HaMaxSmartPowerSensor(Entity):
    def __init__(self, coordinator, device_unique_id, device_name, port_id, port_name, device_version, device_model):
        self._coordinator = coordinator
        self._device_unique_id = device_unique_id
        self._device_name = device_name
        self._port_id = port_id
        self._port_unique_id = f"{device_unique_id}_{port_id}"
        self._port_name = f"{device_name} {port_name}"
        self._device_version = device_version
        self._device_model = device_model
        self._power_data = None
        self._attr_device_info = self.device_info
        self._attr_unique_id = self.unique_id

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
        return f"{self._port_name} Power"

    @property
    def unique_id(self):
        return f"{self._device_unique_id}_{self._port_id}_power"


    async def async_update(self, now=None):
        _LOGGER.debug("Entering update")
        await self._coordinator.async_refresh()
        coordinator_data = self._coordinator.data
        watt_list = coordinator_data['watt']
        _LOGGER.debug("watt_list has been populated with %s",watt_list)
        power_data = watt_list[self._port_id - 1]
        _LOGGER.debug("power_data has been populated with %s",power_data)
        if power_data is not None:
            # Check if the device version is 1.30 and convert from milliwatts to watts if true
            _LOGGER.debug("Firmware version is %s",self._device_version)
            _LOGGER.debug("coordinator_data: %s", coordinator_data)
            _LOGGER.debug("watt_list: %s", watt_list)
            _LOGGER.debug("self._port_id: %s", self._port_id)
            _LOGGER.debug("power_data: %s", power_data)
            self._power_data = float(power_data)
            if self._device_version != "1.30":
                self._power_data /= 1000.0
        else:
            self._power_data = 0

    @property
    def unit_of_measurement(self):
        return "W"

    @property
    def state(self):
        return self._power_data or 0

    @property
    def device_class(self):
        return DEVICE_CLASS_POWER
