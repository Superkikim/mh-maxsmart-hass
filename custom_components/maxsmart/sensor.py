# custom_components/maxsmart/sensor.py
"""Platform for sensor integration."""

from __future__ import annotations

import logging
from typing import Optional

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MaxSmartCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MaxSmart sensors from a config entry."""
    coordinator: MaxSmartCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    device_data = config_entry.data
    device_unique_id = device_data["device_unique_id"]
    device_name = device_data["device_name"]
    
    entities = []
    
    # Create master power sensor (total consumption)
    entities.append(
        MaxSmartPowerSensor(
            coordinator=coordinator,
            device_unique_id=device_unique_id,
            device_name=device_name,
            port_id=0,
            port_name="Total Power",
        )
    )
    
    # Create individual port power sensors (assume 6 ports)
    for port_id in range(1, 7):
        entities.append(
            MaxSmartPowerSensor(
                coordinator=coordinator,
                device_unique_id=device_unique_id,
                device_name=device_name,
                port_id=port_id,
                port_name=f"Port {port_id} Power",
            )
        )
    
    async_add_entities(entities)
    _LOGGER.info("Added %d MaxSmart sensor entities", len(entities))

class MaxSmartPowerSensor(CoordinatorEntity[MaxSmartCoordinator], SensorEntity):
    """MaxSmart power sensor entity."""

    def __init__(
        self,
        coordinator: MaxSmartCoordinator,
        device_unique_id: str,
        device_name: str,
        port_id: int,
        port_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        
        self._device_unique_id = device_unique_id
        self._device_name = device_name
        self._port_id = port_id
        self._port_name = port_name
        
        self._attr_unique_id = f"{device_unique_id}_{port_id}_power"
        self._attr_name = f"{device_name} {port_name}"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_suggested_display_precision = 1
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_unique_id)},
            "name": f"MaxSmart {device_name}",
            "manufacturer": "Max Hauri",
            "model": "MaxSmart Power Station",
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and super().available

    @property
    def native_value(self) -> Optional[float]:
        """Return the current power consumption in watts."""
        if not self.coordinator.data:
            return None
            
        try:
            watt_list = self.coordinator.data.get("watt", [])
            
            if self._port_id == 0:  # Total power
                return sum(float(watt) for watt in watt_list)
            else:  # Individual port
                if 1 <= self._port_id <= len(watt_list):
                    return float(watt_list[self._port_id - 1])
                return None
                    
        except (ValueError, TypeError, IndexError):
            return None