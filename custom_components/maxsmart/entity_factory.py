# custom_components/maxsmart/entity_factory.py
"""Smart entity creation based on device capabilities."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MaxSmartCoordinator

_LOGGER = logging.getLogger(__name__)

class MaxSmartEntityFactory:
    """Factory for creating MaxSmart entities based on device capabilities."""
    
    def __init__(self, coordinator: MaxSmartCoordinator, config_entry: ConfigEntry):
        """Initialize the entity factory."""
        self.coordinator = coordinator
        self.config_entry = config_entry
        self.device_data = config_entry.data
        
    @property
    def device_unique_id(self) -> str:
        """Get device unique ID."""
        return self.device_data["device_unique_id"]
    
    @property  
    def device_name(self) -> str:
        """Get device name."""
        return self.device_data["device_name"]
    
    @property
    def device_ip(self) -> str:
        """Get device IP."""
        return self.device_data["device_ip"]
    
    @property
    def firmware_version(self) -> str:
        """Get firmware version."""
        return self.device_data.get("sw_version", "Unknown")
    
    def get_port_count(self) -> int:
        """
        Determine number of ports based on serial number or device data.
        
        Returns:
            Number of ports (1 or 6)
        """
        try:
            # Check serial number pattern (4th character indicates port count)
            serial = self.device_unique_id
            if len(serial) >= 4:
                port_char = serial[3]
                if port_char == '1':
                    return 1  # Single port device
                elif port_char == '6':
                    return 6  # 6-port device
                    
            # Fallback: assume 6 ports for power stations
            _LOGGER.debug("Unable to determine port count from serial %s, assuming 6 ports", serial)
            return 6
            
        except Exception as err:
            _LOGGER.warning("Error determining port count: %s, assuming 6 ports", err)
            return 6
    
    def get_port_names(self) -> List[str]:
        """
        Get port names from config entry data.
        
        Returns:
            List of port names (length matches port count)
        """
        port_count = self.get_port_count()
        port_names = []
        
        for port_id in range(1, port_count + 1):
            port_key = f"port_{port_id}_name"
            port_name = self.device_data.get(port_key, f"Port {port_id}")
            port_names.append(port_name)
            
        return port_names
    
    def get_device_info(self) -> Dict[str, Any]:
        """
        Generate device info for Home Assistant.
        
        Returns:
            Device info dictionary
        """
        port_count = self.get_port_count()
        model = "MaxSmart Smart Plug" if port_count == 1 else "MaxSmart Power Station"
        
        return {
            "identifiers": {("maxsmart", self.device_unique_id)},
            "name": f"MaxSmart {self.device_name}",
            "manufacturer": "Max Hauri", 
            "model": model,
            "sw_version": self.firmware_version,
            "via_device": None,
            "configuration_url": f"http://{self.device_ip}",
        }
    
    def create_switch_entities(self) -> List[Dict[str, Any]]:
        """
        Create switch entity configurations.
        
        Returns:
            List of switch entity configurations
        """
        entities = []
        port_count = self.get_port_count()
        port_names = self.get_port_names()
        device_info = self.get_device_info()
        
        # Master switch (port 0) - only for multi-port devices
        if port_count > 1:
            entities.append({
                "coordinator": self.coordinator,
                "device_unique_id": self.device_unique_id,
                "device_name": self.device_name,
                "port_id": 0,
                "port_name": "Master",
                "unique_id": f"{self.device_unique_id}_0",
                "name": f"{self.device_name} Master",
                "device_info": device_info,
                "is_master": True,
            })
        
        # Individual port switches
        for port_id in range(1, port_count + 1):
            port_name = port_names[port_id - 1]
            
            entities.append({
                "coordinator": self.coordinator,
                "device_unique_id": self.device_unique_id, 
                "device_name": self.device_name,
                "port_id": port_id,
                "port_name": port_name,
                "unique_id": f"{self.device_unique_id}_{port_id}",
                "name": f"{self.device_name} {port_name}",
                "device_info": device_info,
                "is_master": False,
            })
            
        _LOGGER.debug("Created %d switch entities for device %s", len(entities), self.device_name)
        return entities
    
    def create_sensor_entities(self) -> List[Dict[str, Any]]:
        """
        Create sensor entity configurations.
        
        Returns:
            List of sensor entity configurations  
        """
        entities = []
        port_count = self.get_port_count()
        port_names = self.get_port_names()
        device_info = self.get_device_info()
        
        # Total power sensor - only for multi-port devices
        if port_count > 1:
            entities.append({
                "coordinator": self.coordinator,
                "device_unique_id": self.device_unique_id,
                "device_name": self.device_name,
                "port_id": 0,
                "port_name": "Total Power",
                "unique_id": f"{self.device_unique_id}_0_power",
                "name": f"{self.device_name} Total Power",
                "device_info": device_info,
                "is_total": True,
            })
        
        # Individual port power sensors
        for port_id in range(1, port_count + 1):
            port_name = port_names[port_id - 1]
            
            entities.append({
                "coordinator": self.coordinator,
                "device_unique_id": self.device_unique_id,
                "device_name": self.device_name, 
                "port_id": port_id,
                "port_name": port_name,
                "unique_id": f"{self.device_unique_id}_{port_id}_power",
                "name": f"{self.device_name} {port_name} Power",
                "device_info": device_info,
                "is_total": False,
            })
            
        _LOGGER.debug("Created %d sensor entities for device %s", len(entities), self.device_name)
        return entities
    
    def get_entity_counts(self) -> Tuple[int, int]:
        """
        Get expected entity counts for validation.
        
        Returns:
            Tuple of (switch_count, sensor_count)
        """
        port_count = self.get_port_count()
        
        if port_count == 1:
            # Single port: 1 switch, 1 sensor
            switch_count = 1
            sensor_count = 1
        else:
            # Multi-port: master + N ports switches, total + N ports sensors  
            switch_count = port_count + 1  # Master + individual ports
            sensor_count = port_count + 1  # Total + individual ports
            
        return switch_count, sensor_count