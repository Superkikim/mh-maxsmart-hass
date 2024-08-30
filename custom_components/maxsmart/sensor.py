"""Platform for sensor integration."""
import logging
from datetime import timedelta
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from .const import DOMAIN
from .coordinator import MaxSmartCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    _LOGGER.debug("Starting async_setup_entry for power sensors: %s", config_entry.entry_id)

    device_data = config_entry.data
    _LOGGER.debug("Device data loaded: %s", device_data)

    device_unique_id = device_data['device_unique_id']
    device_ip = device_data['device_ip']
    device_name = device_data['device_name']
    device_ports = device_data['ports']
    device_version = device_data['sw_version']
    device_model = 'Maxsmart Smart Plug' if len(device_ports['individual_ports']) == 1 else 'Maxsmart Power Station'

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

    # Create entities
    master_port = device_ports['master']
    _LOGGER.debug("Creating master power sensor entity for port: %s", master_port)
    master_power_sensor_entity = HaMaxSmartPowerSensor(coordinator, device_unique_id, device_name, 0, master_port['port_name'], device_version, device_model)
    _LOGGER.debug("Master power sensor entity created: %s", master_power_sensor_entity)

    _LOGGER.debug("Creating power sensor entities for individual ports")
    power_sensor_entities = [
        HaMaxSmartPowerSensor(coordinator, device_unique_id, device_name, port['port_id'], port['port_name'], device_version, device_model)
        for port in device_ports['individual_ports']
    ]
    _LOGGER.debug("Power sensor entities created: %s", power_sensor_entities)

    # Add all power sensor entities
    _LOGGER.debug("Adding power sensor entities to Home Assistant")
    async_add_entities([master_power_sensor_entity] + power_sensor_entities)
    _LOGGER.debug("Power sensor entities added to Home Assistant")
    _LOGGER.debug("Updating sensor values")
    await coordinator.async_refresh()


class HaMaxSmartPowerSensor(Entity):
    def __init__(self, coordinator, device_unique_id, device_name, port_id, port_name, device_version, device_model):
        _LOGGER.debug("Initializing HaMaxSmartPowerSensor for port %s", port_id)
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
        if self._port_id == 0:
            self._update_signal = f"maxsmart_update_{self._device_unique_id}"
        _LOGGER.debug("HaMaxSmartPowerSensor initialized: %s", self._port_unique_id)

    async def async_added_to_hass(self):
        """Call when entity is added to hass."""
        _LOGGER.debug("Adding HaMaxSmartPowerSensor to hass for port %s", self._port_id)
        if self._port_id == 0:
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass, self._update_signal, self.async_update
                )
            )
        _LOGGER.debug("HaMaxSmartPowerSensor added to hass for port %s", self._port_id)

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
        name = f"{self._port_name} Power"
        _LOGGER.debug("Returning name for port %s: %s", self._port_id, name)
        return name

    @property
    def unique_id(self):
        unique_id = f"{self._device_unique_id}_{self._port_id}_power"
        _LOGGER.debug("Returning unique_id for port %s: %s", self._port_id, unique_id)
        return unique_id

    async def async_update(self):
        """Update the power data using the latest data from the coordinator."""
        _LOGGER.debug("Updating power data for port %s", self._port_id)
        await self._coordinator.async_refresh()
        watt_list = self._coordinator.data.get('watt', [])
        
        if self._port_id == 0:  # Master port
            self._power_data = sum(float(watt) for watt in watt_list)
        else:
            power_data = watt_list[self._port_id - 1]
            self._power_data = float(power_data)
        
        if self._device_version != "1.30":
            self._power_data /= 1000.0
        
        _LOGGER.debug("Power data for port %s updated to %s W", self._port_id, self._power_data)

    @property
    def unit_of_measurement(self):
        _LOGGER.debug("Returning unit of measurement for port %s: W", self._port_id)
        return "W"

    @property
    def state(self):
        _LOGGER.debug("Returning state for port %s: %s W", self._port_id, self._power_data or 0)
        return self._power_data or 0

    @property
    def device_class(self):
        _LOGGER.debug("Returning device class for port %s: SensorDeviceClass.POWER", self._port_id)
        return SensorDeviceClass.POWER
