from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from datetime import timedelta
from maxsmart import MaxSmartDevice
import logging

_LOGGER = logging.getLogger(__name__)

class MaxSmartCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, device_ip):
        self._maxsmart_device = MaxSmartDevice(device_ip)
        super().__init__(hass, _LOGGER, name="MaxSmart", update_interval=timedelta(seconds=5))

    async def _async_update_data(self):
        _LOGGER.debug("Starting data update")
        data = await self.hass.async_add_executor_job(self._maxsmart_device.get_data)
        _LOGGER.debug("Data retrieved: %s", data)
        return data