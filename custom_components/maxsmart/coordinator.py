from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from datetime import timedelta
import maxsmart
import logging

_LOGGER = logging.getLogger(__name__)

class MaxSmartCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, device_ip):
        self._maxsmart_device = maxsmart.device.MaxSmartDevice(device_ip)
        super().__init__(hass, _LOGGER, name="MaxSmart", update_interval=timedelta(seconds=5))

    async def _async_update_data(self):
        """Fetch data from the MaxSmart device."""
        _LOGGER.debug("Starting data update from device at IP: %s", self._maxsmart_device.device_ip)
        try:
            data = await self.hass.async_add_executor_job(self._maxsmart_device.get_data)
            _LOGGER.debug("Data retrieved successfully: %s", data)
            return data
        except Exception as e:
            _LOGGER.error("Failed to fetch data from device: %s", e)
            raise UpdateFailed(f"Error communicating with device: {e}")
