"""Platform for sensor integration."""
import logging
from datetime import timedelta
from homeassistant.const import DEVICE_CLASS_POWER
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from .const import DOMAIN
from maxsmart import MaxSmartDevice

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

    # Create the MaxSmartDevice instance for this device
    maxsmart_device = MaxSmartDevice(device_ip)

    # Create power sensor entities for each individual port
    power_sensor_entities = [
        HaMaxSmartPowerSensor(maxsmart_device, device_unique_id, device_name, port['port_id'], port['port_name'], device_version, device_model)
        for port in device_ports['individual_ports']
    ]

    # Add all power sensor entities
    async_add_entities(power_sensor_entities)

    # Schedule the update() method for each sensor entity at a more frequent interval (e.g., every 5 seconds)
    update_interval_seconds = 5
    update_interval = timedelta(seconds=update_interval_seconds)
    for sensor in power_sensor_entities:
        async_track_time_interval(hass, sensor.update, interval=update_interval)

class HaMaxSmartPowerSensor(Entity):
    def __init__(self, maxsmart_device, device_unique_id, device_name, port_id, port_name, device_version, device_model):
        self._maxsmart_device = maxsmart_device
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

#    def update(self, now=None):
#        self._power_data = self._maxsmart_device.get_power_data(self._port_id)

    def update(self, now=None):
        _LOGGER.debug("Entering update")
        power_data = self._maxsmart_device.get_power_data(self._port_id)
        _LOGGER.debug("power_data has been populated with %s",power_data)
        if power_data is not None:
            # Check if the device version is 1.30 and convert from milliwatts to watts if true
            _LOGGER.debug("Firmware version is %s",self._device_version)
            self._power_data = float(power_data['watt'])
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
