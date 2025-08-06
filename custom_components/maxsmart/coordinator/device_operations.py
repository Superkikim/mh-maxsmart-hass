"""Device operations for MaxSmart devices."""

import logging
from typing import Dict, Any

_LOGGER = logging.getLogger(__name__)


class DeviceOperations:
    """Handles device operations like turning ports on/off and getting device info."""
    
    def __init__(self, coordinator):
        """Initialize device operations."""
        self.coordinator = coordinator
        self.device_name = coordinator.device_name
    
    async def async_turn_on(self, port_id: int) -> bool:
        """Turn on a port - triggers burst mode in intelligent polling."""
        try:
            if not self.coordinator.device or not self.coordinator._initialized:
                _LOGGER.warning("%s Turn ON port %d: Device not initialized", self.device_name, port_id)
                return False

            _LOGGER.debug("%s Turn ON port %d", self.device_name, port_id)
            success = await self.coordinator.device.turn_on_port(port_id)
            
            if success:
                _LOGGER.debug("%s Port %d turned ON successfully", self.device_name, port_id)
            else:
                _LOGGER.warning("%s Failed to turn ON port %d", self.device_name, port_id)
            
            return success
            
        except Exception as err:
            _LOGGER.error("%s Error turning ON port %d: %s", self.device_name, port_id, err)
            return False

    async def async_turn_off(self, port_id: int) -> bool:
        """Turn off a port - triggers burst mode in intelligent polling."""
        try:
            if not self.coordinator.device or not self.coordinator._initialized:
                _LOGGER.warning("%s Turn OFF port %d: Device not initialized", self.device_name, port_id)
                return False

            _LOGGER.debug("%s Turn OFF port %d", self.device_name, port_id)
            success = await self.coordinator.device.turn_off_port(port_id)
            
            if success:
                _LOGGER.debug("%s Port %d turned OFF successfully", self.device_name, port_id)
            else:
                _LOGGER.warning("%s Failed to turn OFF port %d", self.device_name, port_id)
            
            return success
            
        except Exception as err:
            _LOGGER.error("%s Error turning OFF port %d: %s", self.device_name, port_id, err)
            return False

    async def async_get_device_info(self) -> Dict[str, Any]:
        """Get comprehensive device information for diagnostics."""
        try:
            info = {
                "device_name": self.device_name,
                "device_ip": self.coordinator.device_ip,
                "mac_address": self.coordinator.mac_address,
                "initialized": self.coordinator._initialized,
                "device_available": self.coordinator.device is not None,
            }
            
            # Add config entry data
            if self.coordinator.config_entry:
                info.update({
                    "config_entry_id": self.coordinator.config_entry.entry_id,
                    "device_unique_id": self.coordinator.config_entry.data.get("device_unique_id"),
                    "firmware_version": self.coordinator.config_entry.data.get("firmware_version"),
                    "port_count": self.coordinator.config_entry.data.get("port_count"),
                    "hardware_enhanced": self.coordinator.config_entry.data.get("hardware_enhanced"),
                })
            
            # Add device status if available
            if self.coordinator.device and self.coordinator._initialized:
                try:
                    device_status = await self.coordinator.device.get_data()
                    if device_status:
                        info["device_status"] = device_status
                        info["hardware_info"] = self._format_hardware_info()
                except Exception as err:
                    info["device_status_error"] = str(err)
            
            # Add error tracking info
            if self.coordinator.error_tracker:
                info["error_tracking"] = self.coordinator.error_tracker.get_status_summary()
            
            # Add IP recovery info
            if self.coordinator.ip_recovery:
                info["ip_recovery"] = self.coordinator.ip_recovery.get_status()
            
            return info
            
        except Exception as err:
            _LOGGER.error("%s Error getting device info: %s", self.device_name, err)
            return {"error": str(err)}

    def _format_hardware_info(self) -> str:
        """Format hardware information for logging."""
        try:
            if not self.coordinator.device:
                return "Device not available"
            
            version = getattr(self.coordinator.device, 'version', 'Unknown')
            watt_format = getattr(self.coordinator.device, '_watt_format', 'Unknown')
            watt_multiplier = getattr(self.coordinator.device, '_watt_multiplier', 1.0)
            
            return f"Firmware={version}, Format={watt_format}, Multiplier={watt_multiplier}"
            
        except Exception as err:
            return f"Error formatting hardware info: {err}"
