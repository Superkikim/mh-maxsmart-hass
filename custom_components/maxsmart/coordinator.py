# custom_components/maxsmart/coordinator.py
"""Improved MaxSmart coordinator with enhanced error handling and reduced log pollution."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.config_entries import ConfigEntry

from maxsmart import MaxSmartDevice
from maxsmart.exceptions import (
    ConnectionError as MaxSmartConnectionError,
    CommandError,
    DeviceTimeoutError,
    DiscoveryError,
)

_LOGGER = logging.getLogger(__name__)

# Optimal polling interval for HA (max 15 devices = 3 req/sec total)
UPDATE_INTERVAL = timedelta(seconds=5)

class MaxSmartCoordinator(DataUpdateCoordinator):
    """Enhanced coordinator with improved error handling and logging."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the enhanced coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"MaxSmart {config_entry.data['device_name']}",
            update_interval=UPDATE_INTERVAL,
        )
        
        self.config_entry = config_entry
        self.device_ip = config_entry.data["device_ip"]
        self.device_name = config_entry.data["device_name"]
        self.device_unique_id = config_entry.data["device_unique_id"]
        
        # Enhanced device information
        self.cpu_id = config_entry.data.get("cpu_id", "")
        self.mac_address = config_entry.data.get("mac_address", "")
        self.identification_method = config_entry.data.get("identification_method", "fallback")
        
        self.device: Optional[MaxSmartDevice] = None
        self._initialized = False
        
        # Error tracking for intelligent logging
        self._consecutive_errors = 0
        self._last_error_type = None
        self._total_errors = 0
        self._successful_polls = 0

    async def _async_setup(self) -> None:
        """Set up the coordinator and initialize device with improved error handling."""
        if self._initialized:
            return
            
        try:
            _LOGGER.debug("Initializing MaxSmart device: %s (%s)", self.device_name, self.device_ip)
            
            self.device = MaxSmartDevice(self.device_ip)
            await self.device.initialize_device()
            
            self._initialized = True
            self._consecutive_errors = 0
            
            # Log successful initialization with hardware info
            hw_info = self._format_hardware_info()
            _LOGGER.info("MaxSmart device ready: %s (%s)%s", 
                        self.device_name, self.device_ip, hw_info)
            
        except (DiscoveryError, MaxSmartConnectionError) as err:
            error_msg = f"Cannot connect to MaxSmart device {self.device_name} ({self.device_ip}): {err}"
            _LOGGER.error(error_msg)
            raise UpdateFailed(error_msg)
                
        except Exception as err:
            error_msg = f"Unexpected error initializing {self.device_name}: {err}"
            _LOGGER.error(error_msg)
            raise UpdateFailed(error_msg)

    async def _async_update_data(self) -> Dict[str, Any]:
        """Update data with intelligent error logging to reduce log pollution."""
        try:
            data = await self.device.get_data()
            
            # Track successful poll
            self._successful_polls += 1
            
            # Log recovery from errors
            if self._consecutive_errors > 0:
                _LOGGER.info("MaxSmart device %s recovered after %d failed attempts", 
                           self.device_name, self._consecutive_errors)
                self._consecutive_errors = 0
                self._last_error_type = None
                
            # Periodic success logging (every 100 successful polls)
            if self._successful_polls % 100 == 0:
                _LOGGER.debug("MaxSmart device %s: %d successful polls, %d total errors", 
                            self.device_name, self._successful_polls, self._total_errors)
            
            return data
            
        except Exception as err:
            return await self._handle_update_error(err)

    async def _handle_update_error(self, error: Exception) -> None:
        """Handle update errors with intelligent logging."""
        self._consecutive_errors += 1
        self._total_errors += 1
        error_type = type(error).__name__
        
        # Determine if we should log this error
        should_log = self._should_log_error(error_type)
        
        if should_log:
            if self._consecutive_errors == 1:
                # First error - log as warning
                _LOGGER.warning("MaxSmart device %s (%s) error: %s", 
                              self.device_name, self.device_ip, str(error))
            elif self._consecutive_errors == 5:
                # After 5 consecutive errors - log as error
                _LOGGER.error("MaxSmart device %s has failed 5 consecutive times: %s", 
                            self.device_name, str(error))
            elif self._consecutive_errors % 20 == 0:
                # Every 20 errors after that - brief error log
                _LOGGER.error("MaxSmart device %s still failing (%d consecutive errors)", 
                            self.device_name, self._consecutive_errors)
        else:
            # Log at debug level for suppressed errors
            _LOGGER.debug("MaxSmart device %s error #%d: %s", 
                        self.device_name, self._consecutive_errors, str(error))
        
        self._last_error_type = error_type
        
        # Create user-friendly error message
        user_message = self._create_user_friendly_error(error)
        raise UpdateFailed(user_message)

    def _should_log_error(self, error_type: str) -> bool:
        """Determine if an error should be logged based on type and frequency."""
        # Always log the first few errors
        if self._consecutive_errors <= 3:
            return True
            
        # Always log when error type changes
        if error_type != self._last_error_type:
            return True
            
        # Log network errors less frequently
        if error_type in ["ConnectionError", "TimeoutError", "MaxSmartConnectionError"]:
            return self._consecutive_errors % 10 == 0
            
        # Log other errors moderately
        return self._consecutive_errors % 5 == 0

    def _create_user_friendly_error(self, error: Exception) -> str:
        """Create user-friendly error messages."""
        error_type = type(error).__name__
        
        if "Connection" in error_type or "Timeout" in error_type:
            if self._consecutive_errors == 1:
                return f"Device {self.device_name} is unreachable - check network connection"
            else:
                return f"Device {self.device_name} unreachable ({self._consecutive_errors} attempts)"
                
        elif "Command" in error_type:
            return f"Device {self.device_name} command failed - device may be busy"
            
        else:
            return f"Device {self.device_name} error: {str(error)}"

    def _format_hardware_info(self) -> str:
        """Format hardware information for logging."""
        hw_parts = []
        
        if self.identification_method and self.identification_method != "fallback":
            hw_parts.append(f"ID: {self.identification_method.replace('_', ' ').title()}")
            
        if self.cpu_id:
            hw_parts.append(f"CPU: {self.cpu_id[:8]}...")
            
        if self.mac_address:
            hw_parts.append(f"MAC: {self.mac_address}")
            
        return f" [{', '.join(hw_parts)}]" if hw_parts else ""

    async def async_turn_on(self, port_id: int) -> bool:
        """Turn on a port with improved error handling."""
        if not self._initialized:
            await self._async_setup()
            
        try:
            _LOGGER.debug("Turning on port %d for %s", port_id, self.device_name)
            await self.device.turn_on(port_id)
            
            # Force immediate refresh
            await self.async_request_refresh()
            
            _LOGGER.debug("Port %d turned on successfully for %s", port_id, self.device_name)
            return True
            
        except Exception as err:
            _LOGGER.warning("Failed to turn on port %d for %s: %s", port_id, self.device_name, err)
            return False

    async def async_turn_off(self, port_id: int) -> bool:
        """Turn off a port with improved error handling."""
        if not self._initialized:
            await self._async_setup()
            
        try:
            _LOGGER.debug("Turning off port %d for %s", port_id, self.device_name)
            await self.device.turn_off(port_id)
            
            # Force immediate refresh
            await self.async_request_refresh()
            
            _LOGGER.debug("Port %d turned off successfully for %s", port_id, self.device_name)
            return True
            
        except Exception as err:
            _LOGGER.warning("Failed to turn off port %d for %s: %s", port_id, self.device_name, err)
            return False

    async def async_get_device_info(self) -> Dict[str, Any]:
        """Get comprehensive device information for diagnostics."""
        if not self._initialized:
            await self._async_setup()
            
        try:
            base_info = {
                "name": self.device_name,
                "ip": self.device_ip,
                "unique_id": self.device_unique_id,
                "coordinator_name": self.name,
                "update_interval": self.update_interval.total_seconds(),
                "initialized": self._initialized,
                
                # Enhanced identification
                "cpu_id": self.cpu_id,
                "mac_address": self.mac_address,
                "identification_method": self.identification_method,
                
                # Error statistics
                "consecutive_errors": self._consecutive_errors,
                "total_errors": self._total_errors,
                "successful_polls": self._successful_polls,
                "last_error_type": self._last_error_type,
            }
            
            # Add device-specific info if available
            if self.device:
                try:
                    device_specific = {
                        "firmware": getattr(self.device, 'version', 'Unknown'),
                        "data_format": getattr(self.device, '_watt_format', 'Unknown'),
                        "conversion_factor": getattr(self.device, '_watt_multiplier', 1.0),
                    }
                    base_info.update(device_specific)
                    
                    # Add port names if available
                    if hasattr(self.device, 'port_names') and self.device.port_names:
                        base_info["port_names"] = self.device.port_names
                        
                except Exception as err:
                    base_info["device_info_error"] = str(err)
                    
            return base_info
            
        except Exception as err:
            _LOGGER.error("Error getting device info for %s: %s", self.device_name, err)
            return {"error": str(err)}

    async def async_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        if not self._initialized:
            return {
                "status": "not_initialized", 
                "error": "Device not initialized",
                "device_name": self.device_name,
                "device_ip": self.device_ip
            }
            
        try:
            # Use device's built-in health check if available
            if hasattr(self.device, 'health_check'):
                health = await self.device.health_check()
                health.update({
                    "device_name": self.device_name,
                    "consecutive_errors": self._consecutive_errors,
                    "total_errors": self._total_errors,
                    "identification_method": self.identification_method,
                })
                return health
            else:
                # Fallback health check
                data = await self.device.get_data()
                return {
                    "status": "healthy",
                    "device_name": self.device_name,
                    "device_ip": self.device_ip,
                    "last_update": self.last_update_success,
                    "data_valid": bool(data.get("switch") and data.get("watt")),
                    "consecutive_errors": self._consecutive_errors,
                    "total_errors": self._total_errors,
                }
                
        except Exception as err:
            return {
                "status": "unhealthy", 
                "error": str(err),
                "device_name": self.device_name,
                "device_ip": self.device_ip,
                "last_update": self.last_update_success,
                "consecutive_errors": self._consecutive_errors,
                "total_errors": self._total_errors,
            }

    async def async_reload_from_config(self) -> None:
        """Reload coordinator when config entry is updated."""
        _LOGGER.info("Reloading coordinator for %s due to config change", self.device_name)
        
        # Update internal references
        self.device_name = self.config_entry.data["device_name"]
        self.name = f"MaxSmart {self.device_name}"
        
        # Force data refresh
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        """Shutdown coordinator with proper cleanup."""
        _LOGGER.debug("Shutting down coordinator for %s", self.device_name)
        
        if self.device:
            try:
                await self.device.close()
                _LOGGER.debug("Device connection closed: %s", self.device_ip)
            except Exception as err:
                _LOGGER.warning("Error closing device connection for %s: %s", self.device_name, err)
        
        self._initialized = False
        self.device = None