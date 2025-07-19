# custom_components/maxsmart/__init__.py
"""The Max Hauri MaxSmart Power Devices integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import MaxSmartCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MaxSmart from a config entry."""
    _LOGGER.info("Setting up MaxSmart integration for: %s", entry.title)
    
    device_ip = entry.data["device_ip"]
    
    try:
        # Initialize coordinator
        coordinator = MaxSmartCoordinator(hass, device_ip)
        
        # Perform initial data fetch
        await coordinator.async_config_entry_first_refresh()
        
        # Store coordinator
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator
        
        # Setup platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        _LOGGER.info("MaxSmart integration setup completed for: %s", device_ip)
        return True
        
    except Exception as err:
        _LOGGER.error("Failed to setup MaxSmart integration: %s", err)
        raise ConfigEntryNotReady(f"Unable to connect to device {device_ip}: {err}")

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading MaxSmart integration: %s", entry.title)
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Shutdown coordinator
        coordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_shutdown()
        
        # Remove from hass data
        hass.data[DOMAIN].pop(entry.entry_id)
        
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    
    return unload_ok