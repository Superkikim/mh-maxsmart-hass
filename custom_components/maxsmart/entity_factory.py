# custom_components/maxsmart/entity_factory.py
"""Enhanced entity creation with smart port logic, simplified naming, and IP display."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MaxSmartCoordinator

_LOGGER = logging.getLogger(__name__)

class MaxSmartEntityFactory:
    """Enhanced factory for creating MaxSmart entities with smart port logic."""
    
    def __init__(self, coordinator: MaxSmartCoordinator, config_entry: ConfigEntry):
        """Initialize the enhanced entity factory."""
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
        fw_version = self.device_data.get("sw_version", "Unknown")
        _LOGGER.debug("ENTITY_FACTORY: Firmware version from device_data: %s", fw_version)
        _LOGGER.debug("ENTITY_FACTORY: Device data keys: %s", list(self.device_data.keys()))
        return fw_version
    
    @property
    def cpu_id(self) -> str:
        """Get CPU ID if available."""
        # Support both old (cpu_id) and new (cpuid) keys for migration compatibility
        return self.device_data.get("cpuid", self.device_data.get("cpu_id", ""))
    
    @property
    def mac_address(self) -> str:
        """Get MAC address if available."""
        # Support both old (mac_address) and new (mac) keys for migration compatibility
        return self.device_data.get("mac", self.device_data.get("mac_address", ""))

    @property
    def serial_number(self) -> str:
        """Get serial number if available."""
        # Support both new (sn) and old (udp_serial) keys for migration compatibility
        return self.device_data.get("sn", self.device_data.get("udp_serial", ""))

    @property
    def identification_method(self) -> str:
        """Get identification method used."""
        return self.device_data.get("identification_method", "fallback")
    
    def get_port_count(self) -> int:
        """
        Determine number of ports using enhanced detection methods.
        
        Returns:
            Number of ports (1 or 6)
        """
        # Method 1: Use stored port count if available
        stored_count = self.device_data.get("port_count")
        if stored_count and isinstance(stored_count, int) and stored_count in [1, 6]:
            _LOGGER.debug("Using stored port count: %d", stored_count)
            return stored_count
        
        # Method 2: Count configured port names (most reliable)
        configured_ports = 0
        for port_id in range(1, 7):  # Check up to 6 ports
            port_key = f"port_{port_id}_name"
            if port_key in self.device_data:
                configured_ports = port_id
        
        if configured_ports > 0:
            _LOGGER.debug("Detected %d ports from configured names", configured_ports)
            return configured_ports
        
        # Method 3: Check serial number pattern (legacy method)
        try:
            serial = self.device_unique_id
            if serial.startswith(("cpu_", "mac_", "sn_")):
                # Extract the actual serial/ID part
                actual_id = serial.split("_", 1)[1]
                if len(actual_id) >= 4:
                    # For UDP serials, 4th character indicates port count
                    if serial.startswith("sn_"):
                        port_char = actual_id[3]
                        if port_char == '1':
                            _LOGGER.debug("Detected 1-port device from serial pattern")
                            return 1
                        elif port_char == '6':
                            _LOGGER.debug("Detected 6-port device from serial pattern")
                            return 6
        except Exception as err:
            _LOGGER.debug("Error parsing device ID for port count: %s", err)
            
        # Default fallback - assume 6 ports for power stations
        _LOGGER.debug("Using default port count: 6")
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
        Generate enhanced device info for Home Assistant with hardware details and IP address.
        
        Returns:
            Enhanced device info dictionary with hardware identifiers and IP
        """
        port_count = self.get_port_count()
        model = "MaxSmart Smart Plug" if port_count == 1 else "MaxSmart Power Station"
        
        # Base device info with device name prominently displayed
        device_info = {
            "identifiers": {("maxsmart", self.device_unique_id)},
            "name": self.device_name,  # 🎯 Display device name prominently
            "manufacturer": "Max Hauri", 
            "model": model,
            "sw_version": self.firmware_version,
            "via_device": None,
            "configuration_url": f"http://{self.device_ip}",
        }
        
        # Add essential hardware information for user visibility
        hw_details = []

        # Add IP address (always visible)
        hw_details.append(f"IP: {self.device_ip}")

        # Add serial number if available (important for identification)
        if self.serial_number:
            hw_details.append(f"SN: {self.serial_number}")

        # Add MAC address if available (useful for network identification)
        if self.mac_address:
            hw_details.append(f"MAC: {self.mac_address}")

        # Add hardware details to model description (removed CPU ID and ID method - not user-friendly)
        if hw_details:
            device_info["model"] = f"{model} ({', '.join(hw_details)})"
            
        # Add serial number if available (use modern 'sn' field or legacy 'udp_serial')
        if self.serial_number:
            device_info["serial_number"] = self.serial_number
            
        return device_info
    
    def create_switch_entities(self) -> List[Dict[str, Any]]:
        """
        Create smart switch entity configurations based on port count.
        
        1 port = No master, just the single port
        6 ports = Master + 6 individual ports
        
        Returns:
            List of switch entity configurations with simplified naming
        """
        entities = []
        port_count = self.get_port_count()
        port_names = self.get_port_names()
        device_info = self.get_device_info()
        
        # Smart logic: 1 port vs 6 ports
        if port_count == 1:
            # Single port device: NO master, just the port
            port_name = port_names[0]
            
            entities.append({
                "coordinator": self.coordinator,
                "device_unique_id": self.device_unique_id,
                "device_name": self.device_name,
                "port_id": 1,
                "port_name": port_name,
                "unique_id": f"{self.device_unique_id}_1",
                "name": port_name,  # 🎯 Simplified: just port name
                "device_info": device_info,
                "is_master": False,
                # Enhanced metadata
                "cpu_id": self.cpu_id,
                "mac_address": self.mac_address,
                "identification_method": self.identification_method,
            })
            
        else:
            # Multi-port device: Master + individual ports
            
            # Master switch (port 0)
            entities.append({
                "coordinator": self.coordinator,
                "device_unique_id": self.device_unique_id,
                "device_name": self.device_name,
                "port_id": 0,
                "port_name": "Master",
                "unique_id": f"{self.device_unique_id}_0",
                "name": "Master",  # 🎯 Simplified: just "Master"
                "device_info": device_info,
                "is_master": True,
                # Enhanced metadata
                "cpu_id": self.cpu_id,
                "mac_address": self.mac_address,
                "identification_method": self.identification_method,
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
                    "name": port_name,  # 🎯 Simplified: just port name
                    "device_info": device_info,
                    "is_master": False,
                    # Enhanced metadata
                    "cpu_id": self.cpu_id,
                    "mac_address": self.mac_address,
                    "identification_method": self.identification_method,
                })
            
        _LOGGER.debug("Created %d switch entities for %s (%d-port device, method: %s)", 
                     len(entities), self.device_name, port_count, self.identification_method)
        return entities
    
    def create_sensor_entities(self) -> List[Dict[str, Any]]:
        """
        Create smart sensor entity configurations based on port count.
        
        1 port = Just the single port power sensor
        6 ports = Total power + 6 individual port sensors
        
        Returns:
            List of sensor entity configurations with simplified naming
        """
        entities = []
        port_count = self.get_port_count()
        port_names = self.get_port_names()
        device_info = self.get_device_info()
        
        # Smart logic: 1 port vs 6 ports
        if port_count == 1:
            # Single port device: NO total power, just the port power
            port_name = port_names[0]
            
            entities.append({
                "coordinator": self.coordinator,
                "device_unique_id": self.device_unique_id,
                "device_name": self.device_name, 
                "port_id": 1,
                "port_name": port_name,
                "unique_id": f"{self.device_unique_id}_1_power",
                "name": f"{port_name} Power",  # 🎯 Simplified: "Port Power"
                "device_info": device_info,
                "is_total": False,
                # Enhanced metadata
                "cpu_id": self.cpu_id,
                "mac_address": self.mac_address,
                "identification_method": self.identification_method,
            })
            
        else:
            # Multi-port device: Total power + individual ports
            
            # Total power sensor
            entities.append({
                "coordinator": self.coordinator,
                "device_unique_id": self.device_unique_id,
                "device_name": self.device_name,
                "port_id": 0,
                "port_name": "Total Power",
                "unique_id": f"{self.device_unique_id}_0_power",
                "name": "Total Power",  # 🎯 Simplified: just "Total Power"
                "device_info": device_info,
                "is_total": True,
                # Enhanced metadata
                "cpu_id": self.cpu_id,
                "mac_address": self.mac_address,
                "identification_method": self.identification_method,
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
                    "name": f"{port_name} Power",  # 🎯 Simplified: "Port Power"
                    "device_info": device_info,
                    "is_total": False,
                    # Enhanced metadata
                    "cpu_id": self.cpu_id,
                    "mac_address": self.mac_address,
                    "identification_method": self.identification_method,
                })
            
        _LOGGER.debug("Created %d sensor entities for %s (%d-port device, method: %s)", 
                     len(entities), self.device_name, port_count, self.identification_method)
        return entities
    
    def get_entity_counts(self) -> Tuple[int, int]:
        """
        Get expected entity counts for validation.
        
        Returns:
            Tuple of (switch_count, sensor_count)
        """
        port_count = self.get_port_count()
        
        if port_count == 1:
            # Single port: 1 switch, 1 sensor (no master, no total)
            switch_count = 1
            sensor_count = 1
        else:
            # Multi-port: master + N ports switches, total + N ports sensors  
            switch_count = port_count + 1  # Master + individual ports
            sensor_count = port_count + 1  # Total + individual ports
            
        return switch_count, sensor_count
    
    def get_diagnostics_info(self) -> Dict[str, Any]:
        """
        Get comprehensive diagnostics information for troubleshooting.
        
        Returns:
            Dictionary with all device and configuration information
        """
        return {
            # Device identification
            "device_unique_id": self.device_unique_id,
            "device_name": self.device_name,
            "device_ip": self.device_ip,
            
            # Hardware information
            "cpu_id": self.cpu_id,
            "mac_address": self.mac_address,  # This uses the property which handles both keys
            "udp_serial": self.device_data.get("udp_serial", ""),
            "identification_method": self.identification_method,
            
            # Device capabilities
            "firmware_version": self.firmware_version,
            "port_count": self.get_port_count(),
            "port_names": self.get_port_names(),
            
            # Configuration data
            "config_entry_data": dict(self.device_data),
            
            # Entity counts
            "expected_switches": self.get_entity_counts()[0],
            "expected_sensors": self.get_entity_counts()[1],
            
            # Coordinator info
            "coordinator_name": self.coordinator.name,
            "coordinator_device_ip": self.coordinator.device_ip,
        }