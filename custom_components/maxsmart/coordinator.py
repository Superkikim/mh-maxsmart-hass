# custom_components/maxsmart/coordinator.py
"""MaxSmart coordinator using maxsmart 2.0.0 async API with circuit breaker."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from maxsmart import MaxSmartDevice
from maxsmart.exceptions import (
    ConnectionError as MaxSmartConnectionError,
    CommandError,
    StateError,
    FirmwareError,
    DeviceTimeoutError,
)

_LOGGER = logging.getLogger(__name__)

class MaxSmartCoordinator(DataUpdateCoordinator):
    """Coordinator for MaxSmart device with circuit breaker and error handling."""

    def __init__(self, hass: HomeAssistant, device_ip: str) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="MaxSmart",
            update_interval=timedelta(seconds=5),
        )
        
        self.device_ip = device_ip
        self.device: Optional[MaxSmartDevice] = None
        self._initialized = False
        self._consecutive_failures = 0
        self._max_failures = 3
        self._circuit_breaker_open = False
        self._update_count = 0  # For debugging
        
    async def _async_setup(self) -> None:
        """Set up the coordinator and initialize device."""
        if self._initialized:
            return
            
        try:
            self.device = MaxSmartDevice(self.device_ip)
            await self.device.initialize_device()
            self._initialized = True
            self._consecutive_failures = 0
            self._circuit_breaker_open = False
            _LOGGER.info("MaxSmart device initialized: %s", self.device_ip)
            
        except Exception as err:
            _LOGGER.error("Failed to initialize MaxSmart device %s: %s", self.device_ip, err)
            raise UpdateFailed(f"Failed to initialize device: {err}")

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from the device."""
        # Circuit breaker check
        if self._circuit_breaker_open:
            if self._consecutive_failures < self._max_failures * 2:
                _LOGGER.debug("Circuit breaker open, skipping update")
                raise UpdateFailed("Circuit breaker open")
            else:
                # Try to reset circuit breaker
                _LOGGER.info("Attempting to reset circuit breaker")
                self._circuit_breaker_open = False
                self._consecutive_failures = self._max_failures - 1

        # Ensure device is initialized
        if not self._initialized:
            await self._async_setup()

        try:
            # Get device data using async API
            data = await self.device.get_data()
            
            # Reset failure counter on success
            self._consecutive_failures = 0
            self._circuit_breaker_open = False
            self._update_count += 1
            
            _LOGGER.debug("Data retrieved from %s (update #%d): %s", 
                         self.device_ip, self._update_count, data)
            return data
            
        except (MaxSmartConnectionError, DeviceTimeoutError) as err:
            self._consecutive_failures += 1
            _LOGGER.warning(
                "Connection error for device %s (attempt %d/%d): %s",
                self.device_ip, self._consecutive_failures, self._max_failures, err
            )
            
            if self._consecutive_failures >= self._max_failures:
                self._circuit_breaker_open = True
                _LOGGER.error(
                    "Circuit breaker opened for device %s after %d failures",
                    self.device_ip, self._consecutive_failures
                )
            
            raise UpdateFailed(f"Connection error: {err}")
            
        except Exception as err:
            self._consecutive_failures += 1
            _LOGGER.error(
                "Unexpected error for device %s: %s", self.device_ip, err
            )
            raise UpdateFailed(f"Unexpected error: {err}")

    async def async_turn_on(self, port_id: int) -> bool:
        """Turn on a port."""
        if not self._initialized:
            await self._async_setup()
            
        try:
            await self.device.turn_on(port_id)
            # Force immediate data refresh after command
            await self.async_request_refresh()
            return True
            
        except (CommandError, MaxSmartConnectionError) as err:
            _LOGGER.error("Failed to turn on port %d: %s", port_id, err)
            return False
        except Exception as err:
            _LOGGER.error("Unexpected error turning on port %d: %s", port_id, err)
            return False

    async def async_turn_off(self, port_id: int) -> bool:
        """Turn off a port."""
        if not self._initialized:
            await self._async_setup()
            
        try:
            await self.device.turn_off(port_id)
            # Force immediate data refresh after command
            await self.async_request_refresh()
            return True
            
        except (CommandError, MaxSmartConnectionError) as err:
            _LOGGER.error("Failed to turn off port %d: %s", port_id, err)
            return False
        except Exception as err:
            _LOGGER.error("Unexpected error turning off port %d: %s", port_id, err)
            return False

    def async_get_power_data(self, port_id: int) -> Optional[float]:
        """Get power consumption for a specific port from cached data."""
        if not self.data:
            return None
            
        try:
            watt_list = self.data.get("watt", [])
            
            if port_id == 0:  # Master - total consumption
                return sum(float(watt) for watt in watt_list)
            elif 1 <= port_id <= len(watt_list):
                return float(watt_list[port_id - 1])
            else:
                return None
                
        except (ValueError, TypeError, IndexError):
            return None

    async def async_get_port_state(self, port_id: int) -> Optional[bool]:
        """Get switch state for a specific port from cached data."""
        if not self.data:
            return None
            
        try:
            switch_list = self.data.get("switch", [])
            
            if port_id == 0:  # Master - any port on
                return any(state == 1 for state in switch_list)
            elif 1 <= port_id <= len(switch_list):
                return switch_list[port_id - 1] == 1
            else:
                return None
                
        except (TypeError, IndexError):
            return None

    @property
    def is_available(self) -> bool:
        """Return if the device is available."""
        return self._initialized and not self._circuit_breaker_open

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator and close device connection."""
        if self.device:
            try:
                await self.device.close()
                _LOGGER.debug("MaxSmart device connection closed: %s", self.device_ip)
            except Exception as err:
                _LOGGER.warning("Error closing device connection: %s", err)
        
        self._initialized = False