# custom_components/maxsmart/sensor.py
"""Platform for sensor integration using MaxSmart 2.0.0 coordinator."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

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
    """Set up MaxSmart power sensors from a config entry."""
    coordinator: MaxSmartCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    device_data = config_entry.data
    device_unique_id = device_data["device_unique_id"]
    device_name = device_data["device_name"]
    device_ports = device_data["ports"]
    device_version = device_data["sw_version"]
    
    # Determine device model based on port count
    port_count = len(device_ports["individual_ports"])
    device_model = "MaxSmart Smart Plug" if port_count == 1 else "MaxSmart Power Station"
    
    entities = []
    
    # Create master power sensor (port 0 - total consumption)
    master_port = device_ports["master"]
    entities.append(
        MaxSmartPowerSensor(
            coordinator=coordinator,
            device_unique_id=device_unique_id,
            device_name=device_name,
            device_version=device_version,
            device_model=device_model,
            port_id=0,
            port_name=master_port["port_name"],
        )
    )
    
    # Create individual port power sensors
    for port in device_ports["individual_ports"]:
        entities.append(
            MaxSmartPowerSensor(
                coordinator=coordinator,
                device_unique_id=device_unique_id,
                device_name=device_name,
                device_version=device_version,
                device_model=device_model,
                port_id=port["port_id"],
                port_name=port["port_name"],
            )
        )
    
    async_add_entities(entities)
    _LOGGER.debug("Added %d MaxSmart power sensor entities", len(entities))

class MaxSmartPowerSensor(CoordinatorEntity[MaxSmartCoordinator], SensorEntity):
    """Representation of a MaxSmart power consumption sensor."""

    def __init__(
        self,
        coordinator: MaxSmartCoordinator,
        device_unique_id: str,
        device_name: str,
        device_version: str,
        device_model: str,
        port_id: int,
        port_name: str,
    ) -> None:
        """Initialize the power sensor entity."""
        super().__init__(coordinator)
        
        self._device_unique_id = device_unique_id
        self._device_name = device_name
        self._device_version = device_version
        self._device_model = device_model
        self._port_id = port_id
        self._port_name = port_name
        
        # Entity attributes
        self._attr_unique_id = f"{device_unique_id}_{port_id}_power"
        self._attr_name = f"{device_name} {port_name} Power"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_suggested_display_precision = 1
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_unique_id)},
            "name": f"Maxsmart {device_name}",
            "manufacturer": "Max Hauri",
            "model": device_model,
            "sw_version": device_version,
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.is_available and super().available

    @property
    def native_value(self) -> Optional[float]:
        """Return the current power consumption in watts."""
        if not self.coordinator.data:
            return None
            
        try:
            watt_list = self.coordinator.data.get("watt", [])
            
            if self._port_id == 0:  # Master sensor - total consumption
                # Sum all individual port consumptions
                total_power = sum(float(watt) for watt in watt_list)
                return round(total_power, 1)
                
            else:  # Individual port sensor
                if 1 <= self._port_id <= len(watt_list):
                    power = float(watt_list[self._port_id - 1])
                    return round(power, 1)
                else:
                    _LOGGER.warning("Invalid port_id %d for power data", self._port_id)
                    return None
                    
        except (ValueError, TypeError, IndexError) as err:
            _LOGGER.error("Error getting power data for port %d: %s", self._port_id, err)
            return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        attributes = {
            "port_id": self._port_id,
            "device_ip": self.coordinator.device_ip,
            "firmware_version": self._device_version,
        }
        
        # Add switch state information
        if self.coordinator.data:
            try:
                switch_list = self.coordinator.data.get("switch", [])
                
                if self._port_id == 0:  # Master
                    active_ports = sum(1 for state in switch_list if state == 1)
                    attributes["active_ports"] = active_ports
                    attributes["total_ports"] = len(switch_list)
                else:  # Individual port
                    if 1 <= self._port_id <= len(switch_list):
                        attributes["switch_state"] = "on" if switch_list[self._port_id - 1] == 1 else "off"
                        
            except (TypeError, IndexError) as err:
                _LOGGER.debug("Could not get switch state for attributes: %s", err)
        
        # Add data format information (useful for debugging)
        if hasattr(self.coordinator.device, '_watt_format'):
            attributes["data_format"] = getattr(self.coordinator.device, '_watt_format')
            
        return attributes

    @property
    def icon(self) -> str:
        """Return the icon for the sensor."""
        if self._port_id == 0:
            # Master sensor icon
            return "mdi:flash"
        else:
            # Individual port icon based on power consumption
            power = self.native_value
            if power is None or power == 0:
                return "mdi:flash-off"
            elif power < 10:
                return "mdi:flash-outline"
            else:
                return "mdi:flash"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        _LOGGER.debug("Added MaxSmart power sensor: %s", self._attr_name)