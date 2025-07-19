# custom_components/maxsmart/coordinator.py
"""MaxSmart coordinator optimized for 5s polling with maxsmart 2.0.0."""

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

# Optimal polling for HA with max 15 devices = 3 req/sec total
UPDATE_INTERVAL = timedelta(seconds=5)

class MaxSmartCoordinator(DataUpdateCoordinator):
    """Coordinator for MaxSmart device with 5s optimal polling."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
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
        
        self.device: Optional[MaxSmartDevice] = None
        self._initialized = False
        self._init_error_count = 0
        self._max_init_retries = 3

    async def _async_setup(self) -> None:
        """Set up the coordinator and initialize device."""
        if self._initialized:
            return
            
        try:
            _LOGGER.debug("Initializing MaxSmart device at %s", self.device_ip)
            self.device = MaxSmartDevice(self.device_ip)
            await self.device.initialize_device()
            
            self._initialized = True
            self._init_error_count = 0
            
            # Log initialization success with device info
            _LOGGER.info(
                "MaxSmart device initialized: %s (%s) - FW: %s, Format: %s", 
                self.device_name,
                self.device_ip,
                getattr(self.device, 'version', 'Unknown'),
                getattr(self.device, '_watt_format', 'Unknown')
            )
            
        except (DiscoveryError, MaxSmartConnectionError) as err:
            self._init_error_count += 1
            _LOGGER.error(
                "Failed to initialize MaxSmart device %s (attempt %d/%d): %s", 
                self.device_ip, self._init_error_count, self._max_init_retries, err
            )
            
            if self._init_error_count >= self._max_init_retries:
                raise UpdateFailed(f"Device initialization failed after {self._max_init_retries} attempts: {err}")
            else:
                raise UpdateFailed(f"Device initialization failed: {err}")
                
        except Exception as err:
            self._init_error_count += 1
            _LOGGER.error(
                "Unexpected error initializing MaxSmart device %s: %s", 
                self.device_ip, err
            )
            raise UpdateFailed(f"Unexpected initialization error: {err}")

    async def _async_update_data(self) -> Dict[str, Any]:
        try:
            _LOGGER.info("=== STARTING DATA FETCH for %s ===", self.device_name)
            data = await self.device.get_data()
            _LOGGER.info("=== SUCCESS DATA FETCH for %s ===", self.device_name) 
            return data
        except Exception as err:
            _LOGGER.error("=== RAW ERROR for %s: %s (type: %s) ===", 
                        self.device_name, str(err), type(err).__name__)
            import traceback
            _LOGGER.error("=== FULL TRACEBACK ===\n%s", traceback.format_exc())
            raise UpdateFailed(f"Data fetch failed: {err}")
    

    async def async_turn_on(self, port_id: int) -> bool:
        """Turn on a port with immediate refresh."""
        if not self._initialized:
            await self._async_setup()
            
        try:
            _LOGGER.debug("Turning on port %d for device %s", port_id, self.device_name)
            await self.device.turn_on(port_id)
            
            # Force immediate data refresh after command
            await self.async_request_refresh()
            
            _LOGGER.debug("Successfully turned on port %d for device %s", port_id, self.device_name)
            return True
            
        except (CommandError, MaxSmartConnectionError) as err:
            _LOGGER.error("Failed to turn on port %d for device %s: %s", port_id, self.device_name, err)
            return False
        except Exception as err:
            _LOGGER.error("Unexpected error turning on port %d for device %s: %s", port_id, self.device_name, err)
            return False

    async def async_turn_off(self, port_id: int) -> bool:
        """Turn off a port with immediate refresh."""
        if not self._initialized:
            await self._async_setup()
            
        try:
            _LOGGER.debug("Turning off port %d for device %s", port_id, self.device_name)
            await self.device.turn_off(port_id)
            
            # Force immediate data refresh after command
            await self.async_request_refresh()
            
            _LOGGER.debug("Successfully turned off port %d for device %s", port_id, self.device_name)
            return True
            
        except (CommandError, MaxSmartConnectionError) as err:
            _LOGGER.error("Failed to turn off port %d for device %s: %s", port_id, self.device_name, err)
            return False
        except Exception as err:
            _LOGGER.error("Unexpected error turning off port %d for device %s: %s", port_id, self.device_name, err)
            return False

    async def async_get_device_info(self) -> Dict[str, Any]:
        """Get extended device information for diagnostics."""
        if not self._initialized:
            await self._async_setup()
            
        try:
            device_info = {
                "name": self.device.name,
                "ip": self.device.ip,
                "serial": self.device.sn,
                "firmware": self.device.version,
                "data_format": getattr(self.device, '_watt_format', 'Unknown'),
                "conversion_factor": getattr(self.device, '_watt_multiplier', 1.0),
                "initialized": self._initialized,
                "coordinator_name": self.name,
                "update_interval": self.update_interval.total_seconds(),
            }
            
            # Add port names if available
            if hasattr(self.device, 'port_names') and self.device.port_names:
                device_info["port_names"] = self.device.port_names
                
            return device_info
            
        except Exception as err:
            _LOGGER.error("Error getting device info for %s: %s", self.device_name, err)
            return {"error": str(err)}

    async def async_health_check(self) -> Dict[str, Any]:
        """Perform health check on the device."""
        if not self._initialized:
            return {"status": "not_initialized", "error": "Device not initialized"}
            
        try:
            # Use the device's built-in health check if available
            if hasattr(self.device, 'health_check'):
                return await self.device.health_check()
            else:
                # Fallback: basic connectivity test
                data = await self.device.get_data()
                return {
                    "status": "healthy",
                    "last_update": self.last_update_success,
                    "data_valid": bool(data.get("switch") and data.get("watt")),
                }
                
        except Exception as err:
            return {
                "status": "unhealthy", 
                "error": str(err),
                "last_update": self.last_update_success,
            }

    async def async_reload_from_config(self) -> None:
        """Reload coordinator when config entry is updated."""
        _LOGGER.info("Reloading coordinator for device %s due to config change", self.device_name)
        
        # Update internal references
        self.device_name = self.config_entry.data["device_name"]
        
        # Update coordinator name
        self.name = f"MaxSmart {self.device_name}"
        
        # Force data refresh to apply any changes
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator and close device connection."""
        _LOGGER.debug("Shutting down coordinator for device %s", self.device_name)
        
        if self.device:
            try:
                await self.device.close()
                _LOGGER.debug("MaxSmart device connection closed: %s", self.device_ip)
            except Exception as err:
                _LOGGER.warning("Error closing device connection for %s: %s", self.device_name, err)
        
        self._initialized = False
        self.device = None

