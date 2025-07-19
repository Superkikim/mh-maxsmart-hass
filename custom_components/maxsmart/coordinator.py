# custom_components/maxsmart/coordinator.py
"""MaxSmart coordinator using maxsmart 2.0.0 async API."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from maxsmart import MaxSmartDevice
from maxsmart.exceptions import (
    ConnectionError as MaxSmartConnectionError,
    CommandError,
    DeviceTimeoutError,
)

_LOGGER = logging.getLogger(__name__)

class MaxSmartCoordinator(DataUpdateCoordinator):
    """Coordinator for MaxSmart device."""

    def __init__(self, hass: HomeAssistant, device_ip: str) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"MaxSmart {device_ip}",
            update_interval=timedelta(seconds=10),
        )
        
        self.device_ip = device_ip
        self.device: Optional[MaxSmartDevice] = None
        self._initialized = False

    async def _async_setup(self) -> None:
        """Set up the coordinator and initialize device."""
        if self._initialized:
            return
            
        try:
            self.device = MaxSmartDevice(self.device_ip)
            await self.device.initialize_device()
            self._initialized = True
            _LOGGER.info("MaxSmart device initialized: %s", self.device_ip)
            
        except Exception as err:
            _LOGGER.error("Failed to initialize MaxSmart device %s: %s", self.device_ip, err)
            raise UpdateFailed(f"Failed to initialize device: {err}")

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from the device."""
        # Ensure device is initialized
        if not self._initialized:
            await self._async_setup()

        try:
            # Get device data using async API
            data = await self.device.get_data()
            _LOGGER.debug("Data retrieved from %s: %s", self.device_ip, data)
            return data
            
        except (MaxSmartConnectionError, DeviceTimeoutError) as err:
            _LOGGER.warning("Connection error for device %s: %s", self.device_ip, err)
            raise UpdateFailed(f"Connection error: {err}")
            
        except Exception as err:
            _LOGGER.error("Unexpected error for device %s: %s", self.device_ip, err)
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

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator and close device connection."""
        if self.device:
            try:
                await self.device.close()
                _LOGGER.debug("MaxSmart device connection closed: %s", self.device_ip)
            except Exception as err:
                _LOGGER.warning("Error closing device connection: %s", err)
        
        self._initialized = False