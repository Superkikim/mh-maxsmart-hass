# custom_components/maxsmart/sensor.py
"""Platform for sensor integration using entity factory."""

from __future__ import annotations

import logging
from typing import Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MaxSmartCoordinator
from .entity_factory import MaxSmartEntityFactory

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MaxSmart sensors from a config entry using entity factory."""
    coordinator: MaxSmartCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    # Create entity factory
    factory = MaxSmartEntityFactory(coordinator, config_entry)
    
    # Generate sensor entity configurations
    sensor_configs = factory.create_sensor_entities()
    
    # Create actual sensor entities
    entities = []
    for config in sensor_configs:
        entities.append(MaxSmartPowerSensor(**config))
    
    async_add_entities(entities, True)
    
    _, expected_count = factory.get_entity_counts()
    _LOGGER.info("Added %d/%d MaxSmart sensor entities for %s", 
                len(entities), expected_count, factory.device_name)

class MaxSmartPowerSensor(CoordinatorEntity[MaxSmartCoordinator], SensorEntity):
    """MaxSmart power sensor entity with smart capabilities."""

    def __init__(
        self,
        coordinator: MaxSmartCoordinator,
        device_unique_id: str,
        device_name: str,
        port_id: int,
        port_name: str,
        unique_id: str,
        name: str,
        device_info: dict,
        is_total: bool,
        **kwargs
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        
        self._device_unique_id = device_unique_id
        self._device_name = device_name
        self._port_id = port_id
        self._port_name = port_name
        self._is_total = is_total
        
        # Entity attributes
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._attr_device_info = device_info
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_suggested_display_precision = 1
        
        # Additional attributes for diagnostics
        self._attr_extra_state_attributes = {
            "port_id": port_id,
            "port_name": port_name,
            "is_total": is_total,
            "device_ip": coordinator.device_ip,
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
            
            if not watt_list:
                return None
                
            if self._is_total:
                # Total power - sum all ports
                try:
                    total = sum(float(watt) for watt in watt_list)
                    return round(total, 1)
                except (ValueError, TypeError) as err:
                    _LOGGER.debug("Error calculating total power: %s", err)
                    return None
            else:
                # Individual port power
                if 1 <= self._port_id <= len(watt_list):
                    try:
                        value = float(watt_list[self._port_id - 1])
                        return round(value, 1)
                    except (ValueError, TypeError) as err:
                        _LOGGER.debug("Error getting power for port %d: %s", self._port_id, err)
                        return None
                return None
                    
        except (TypeError, IndexError) as err:
            _LOGGER.debug("Error getting power data for port %d: %s", self._port_id, err)
            return None

    @property
    def icon(self) -> str:
        """Return the icon for this sensor."""
        if self._is_total:
            return "mdi:flash"
        else:
            # Different icons based on power level
            power = self.native_value
            if power is None or power == 0:
                return "mdi:flash-off"
            elif power < 10:
                return "mdi:flash-outline"
            elif power < 100:
                return "mdi:flash"
            else:
                return "mdi:lightning-bolt"

    @property
    def entity_category(self) -> Optional[str]:
        """Return the entity category."""
        # Power sensors are primary entities, not diagnostic
        return None

    def _update_extra_attributes(self) -> None:
        """Update extra state attributes with current data."""
        if not self.coordinator.data:
            return
            
        try:
            watt_list = self.coordinator.data.get("watt", [])
            switch_list = self.coordinator.data.get("switch", [])
            
            # Add switch state for this port
            if self._is_total:
                active_ports = sum(1 for state in switch_list if state == 1) if switch_list else 0
                self._attr_extra_state_attributes.update({
                    "active_ports": active_ports,
                    "total_ports": len(switch_list) if switch_list else 0,
                })
            else:
                if 1 <= self._port_id <= len(switch_list):
                    port_state = "on" if switch_list[self._port_id - 1] == 1 else "off"
                    self._attr_extra_state_attributes.update({
                        "switch_state": port_state,
                    })
                    
            # Add timestamp of last update - FIXED: use last_update_success
            if self.coordinator.last_update_success:
                self._attr_extra_state_attributes.update({
                    "last_update": self.coordinator.last_update_success,
                })
            
        except Exception as err:
            _LOGGER.debug("Error updating extra attributes for %s: %s", self._attr_name, err)

    async def async_update(self) -> None:
        """Update the entity."""
        await super().async_update()
        self._update_extra_attributes()

    @property
    def should_poll(self) -> bool:
        """No need to poll. Coordinator handles this."""
        return False

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        await super().async_added_to_hass()
        _LOGGER.debug("Added power sensor: %s (port %d)", self._attr_name, self._port_id)

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal."""
        await super().async_will_remove_from_hass()
        _LOGGER.debug("Removing power sensor: %s (port %d)", self._attr_name, self._port_id)