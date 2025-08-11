"""Main MaxSmart coordinator with intelligent polling and conservative IP recovery."""

import asyncio
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
)

from .error_tracking import SmartErrorTracker
from .ip_recovery import ConservativeIPRecovery, IPRecoveryManager
from .polling_manager import PollingManager
from .device_operations import DeviceOperations

from ..messages import (
    log_setup_start, log_setup_success, log_setup_failed,
    log_ip_recovery_start, log_ip_recovery_success, log_ip_recovery_failed,
    log_connection_test_start, log_connection_test_success, log_connection_test_failed,
    log_device_recreated
)

_LOGGER = logging.getLogger(__name__)

# Disable HA polling - we use maxsmart intelligent polling instead
UPDATE_INTERVAL = timedelta(seconds=300)  # Very long interval as fallback only


class MaxSmartCoordinator(DataUpdateCoordinator):
    """Enhanced coordinator with intelligent polling and conservative IP recovery."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator with intelligent polling."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"MaxSmart {config_entry.data['device_name']}",
            update_interval=UPDATE_INTERVAL,
        )
        
        # Core configuration
        self.config_entry = config_entry
        self.device_name = config_entry.data["device_name"]
        self.device_ip = config_entry.data["device_ip"]
        # Support both old (mac_address) and new (mac) keys for migration compatibility
        self.mac_address = config_entry.data.get("mac", config_entry.data.get("mac_address", ""))

        # DEBUG: Log config entry data
        _LOGGER.debug("🔧 COORDINATOR INIT: %s - Config data keys: %s",
                     self.device_name, list(config_entry.data.keys()))
        _LOGGER.debug("🔧 COORDINATOR INIT: %s - MAC from config: '%s'",
                     self.device_name, self.mac_address)
        _LOGGER.debug("🔧 COORDINATOR INIT: %s - Full config data: %s",
                     self.device_name, dict(config_entry.data))
        
        # Device and state
        self.device: Optional[MaxSmartDevice] = None
        self._initialized = False
        self._shutdown_event = asyncio.Event()
        self._discovered_device_info: Optional[Dict[str, Any]] = None
        
        # Component managers
        self.error_tracker = SmartErrorTracker(self.device_name)
        self.ip_recovery = ConservativeIPRecovery(self.device_name, self.mac_address)
        self.ip_recovery_manager = IPRecoveryManager(self)
        self.polling_manager = PollingManager(self)
        self.device_operations = DeviceOperations(self)
        
        # Legacy task references (for cleanup)
        self._error_detection_task = None

    async def async_config_entry_first_refresh(self) -> None:
        """Override first refresh to perform our custom setup."""
        try:
            await self._async_setup()
        except Exception as err:
            _LOGGER.error("Setup failed for %s: %s", self.device_name, err)
            raise UpdateFailed(f"Setup failed: {err}") from err

    async def _async_setup(self) -> None:
        """Set up the coordinator - simplified without startup IP recovery."""
        log_setup_start(self.device_name, self.device_ip)
        
        # Recover missing MAC address if needed (auto-migration)
        await self.ip_recovery_manager.recover_missing_mac_address()
        
        # Try to connect at current IP
        success = await self._try_connect_at_ip(self.device_ip)
        
        if success:
            await self._complete_successful_setup()
        else:
            # Connection failed - create resilient setup for offline device
            self._create_resilient_setup()
            
            # Start offline retry loop
            self.polling_manager.start_offline_retry()

    async def _try_connect_at_ip(self, ip_address: str) -> bool:
        """Try to connect to device at specific IP address."""
        try:
            log_connection_test_start(self.device_name, ip_address)

            from ..discovery import async_discover_device_by_ip
            device_info = await async_discover_device_by_ip(ip_address, enhance_with_hardware=True)

            if device_info:
                log_connection_test_success(self.device_name, ip_address)
                # Store discovered device info for protocol detection
                self._discovered_device_info = device_info
                return True
            else:
                log_connection_test_failed(self.device_name, ip_address, "No device found")
                return False

        except Exception as err:
            log_connection_test_failed(self.device_name, ip_address, str(err))
            return False

    async def _attempt_startup_ip_recovery(self) -> Optional[str]:
        """Attempt IP recovery at startup - limited to one attempt."""
        if not self.mac_address:
            _LOGGER.debug("%s Startup IP recovery: No MAC address available", self.device_name)
            return None
        
        log_ip_recovery_start(self.device_name, self.device_ip, self.mac_address)
        
        try:
            new_ip = await self.ip_recovery_manager.recover_device_ip()
            if new_ip:
                log_ip_recovery_success(self.device_name, self.device_ip, new_ip)
                return new_ip
            else:
                log_ip_recovery_failed(self.device_name)
                return None
        except Exception as e:
            _LOGGER.error("Startup IP recovery failed for %s: %s", self.device_name, e)
            return None

    async def _complete_successful_setup(self) -> None:
        """Complete successful device setup."""
        try:
            # Create and initialize device with protocol detection
            protocol = None
            sn = None

            # Use discovered device info if available (maxsmart 2.1.0 support)
            if self._discovered_device_info:
                protocol = self._discovered_device_info.get('protocol')
                sn = self._discovered_device_info.get('sn')
                _LOGGER.debug("%s Protocol detected from discovery: %s, SN: %s",
                             self.device_name, protocol, sn)

            # Create device with appropriate parameters for maxsmart 2.1.0
            if protocol and sn:
                # UDP V3 device with serial number
                self.device = MaxSmartDevice(self.device_ip, protocol=protocol, sn=sn)
                _LOGGER.debug("%s Creating UDP V3 device with protocol=%s, sn=%s",
                             self.device_name, protocol, sn)
            elif protocol:
                # HTTP or other protocol without serial
                self.device = MaxSmartDevice(self.device_ip, protocol=protocol)
                _LOGGER.debug("%s Creating device with protocol=%s", self.device_name, protocol)
            else:
                # Fallback to auto-detection (legacy behavior)
                self.device = MaxSmartDevice(self.device_ip)
                _LOGGER.debug("%s Creating device with auto-detection", self.device_name)

            await self.device.initialize_device()
            
            # Log device info to verify firmware version and watt multiplier
            log_device_recreated(
                self.device_name,
                getattr(self.device, 'version', 'Unknown'),
                getattr(self.device, '_watt_format', 'Unknown'),
                getattr(self.device, '_watt_multiplier', 1.0)
            )
            
            # Start intelligent polling
            try:
                await self.device.start_adaptive_polling(enable_burst=True)
                # Register callback for real-time data updates
                self.device.register_poll_callback("coordinator", self.polling_manager.on_poll_data)
                _LOGGER.debug("%s adaptive polling started successfully", self.device_name)
                self.polling_manager.start_conservative_error_detection()
            except Exception as err:
                _LOGGER.warning("%s adaptive polling start failed: %s", self.device_name, err)
                # Fallback to periodic polling
                self.polling_manager.start_periodic_polling()

            # Mark as initialized and get initial data
            self._initialized = True
            self.error_tracker.record_successful_poll()
            self.ip_recovery.reset_on_success()

            # Get initial data
            initial_data = await self.device.get_data()
            if initial_data:
                self.async_set_updated_data(initial_data)
            
            log_setup_success(self.device_name)
            
        except Exception as err:
            log_setup_failed(self.device_name, str(err))
            raise

    def _create_resilient_setup(self) -> None:
        """Create resilient setup for offline devices."""
        # Set empty data to allow entity creation
        self.async_set_updated_data({})
        _LOGGER.debug("%s resilient setup: Created with empty data", self.device_name)

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fallback update method for offline devices."""
        try:
            if not self.device or not self._initialized:
                # Return empty data for offline devices to prevent entity errors
                return {}
            
            # Get device data
            data = await self.device.get_data()
            if data:
                self.error_tracker.record_successful_poll()
                # DEBUG: Log data structure
                _LOGGER.debug("🔧 UPDATE DATA: %s - Received data: %s",
                             self.device_name, data)
                return data
            else:
                _LOGGER.warning("🔧 UPDATE DATA: %s - No data received from device",
                               self.device_name)
                raise UpdateFailed("No data received from device")
                
        except (MaxSmartConnectionError, DeviceTimeoutError, CommandError) as err:
            # Record error but don't raise - let intelligent polling handle it
            should_log = self.error_tracker.record_error("polling_error")
            if should_log:
                _LOGGER.warning("%s Fallback polling error: %s", self.device_name, err)
            
            # Return empty data to prevent entity errors
            return {}
        except Exception as err:
            _LOGGER.error("%s Unexpected fallback polling error: %s", self.device_name, err)
            return {}

    # Delegate methods to component managers
    async def async_turn_on(self, port_id: int) -> bool:
        """Turn on a port."""
        return await self.device_operations.async_turn_on(port_id)

    async def async_turn_off(self, port_id: int) -> bool:
        """Turn off a port."""
        return await self.device_operations.async_turn_off(port_id)

    async def async_get_device_info(self) -> Dict[str, Any]:
        """Get comprehensive device information."""
        return await self.device_operations.async_get_device_info()

    async def async_reload_from_config(self) -> None:
        """Reload coordinator when config entry is updated."""
        try:
            _LOGGER.debug("%s Reloading from updated config", self.device_name)
            
            # Update configuration
            old_device_name = self.device_name
            old_ip = self.device_ip
            
            self.device_name = self.config_entry.data["device_name"]
            self.device_ip = self.config_entry.data["device_ip"]
            # Support both old (mac_address) and new (mac) keys for migration compatibility
            self.mac_address = self.config_entry.data.get("mac", self.config_entry.data.get("mac_address", ""))
            
            # Check what changed
            device_name_changed = old_device_name != self.device_name
            ip_changed = old_ip != self.device_ip
            
            if ip_changed:
                await self.ip_recovery_manager._change_device_ip(self.device_ip, "user_options")
            elif device_name_changed:
                _LOGGER.info("Device name updated: %s → %s", old_device_name, self.device_name)
                # Just name changes, no reconnection needed
            else:
                # Only port names changed, coordinator doesn't need to reconnect
                _LOGGER.debug("Port names updated for %s, no coordinator changes needed", self.device_name)
                
        except Exception as err:
            _LOGGER.error("Failed to reload config for %s: %s", self.device_name, err)

    async def async_shutdown(self) -> None:
        """Shutdown coordinator with intelligent polling cleanup."""
        try:
            _LOGGER.debug("%s Shutting down coordinator", self.device_name)
            
            # Signal shutdown
            self._shutdown_event.set()
            
            # Stop all polling tasks
            await self.polling_manager.stop_all_tasks()
            
            # Stop device polling
            if self.device:
                try:
                    await self.device.stop_adaptive_polling()
                    await self.device.close()
                    _LOGGER.debug("%s Intelligent polling stopped and device connection closed", self.device_ip)
                except Exception as err:
                    _LOGGER.debug("Error stopping device during shutdown: %s", err)
            
            self.device = None
            self._initialized = False
            
            _LOGGER.debug("%s Coordinator shutdown completed", self.device_name)
            
        except Exception as err:
            _LOGGER.error("Error during coordinator shutdown for %s: %s", self.device_name, err)
