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

    # Create entities
    master_port = device_ports['master']
    master_power_sensor_entity = HaMaxSmartPowerSensor(coordinator, device_unique_id, device_name, 0, master_port['port_name'], device_version, device_model)

    power_sensor_entities = [
        HaMaxSmartPowerSensor(coordinator, device_unique_id, device_name, port['port_id'], port['port_name'], device_version, device_model)
        for port in device_ports['individual_ports']
    ]

    # Add all power sensor entities
    async_add_entities([master_power_sensor_entity] + power_sensor_entities)

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
        if self._port_id == 0:
            self._update_signal = f"maxsmart_update_{self._device_unique_id}"

    async def async_added_to_hass(self):
        """Call when entity is added to hass."""
        if self._port_id == 0:
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass, self._update_signal, self.async_update
                )
            )

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
        await self._coordinator.async_refresh()
        coordinator_data = self._coordinator.data
        watt_list = coordinator_data['watt']

        if self._port_id == 0:  # Master port
            self._power_data = sum(float(watt) for watt in watt_list)
        else:
            async_dispatcher_send(self.hass, f"maxsmart_update_{self._device_unique_id}")
            power_data = watt_list[self._port_id - 1]
            self._power_data = float(power_data)


        if self._power_data is not None:
            # Check if the device version is 1.30 and convert from milliwatts to watts if true
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
        return SensorDeviceClass.POWER
