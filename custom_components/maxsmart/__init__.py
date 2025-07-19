# custom_components/maxsmart/__init__.py
"""The Max Hauri MaxSmart Power Devices integration."""
from __future__ import annotations

import logging
from typing import Dict, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import MaxSmartCoordinator

_LOGGER = logging.getLogger(__name__)

# Platforms supported by this integration
PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Max Hauri MaxSmart Power Devices from a config entry."""
    _LOGGER.info("Setting up MaxSmart integration for device: %s", entry.title)
    
    # Get device configuration
    device_ip = entry.data["device_ip"]
    device_unique_id = entry.data["device_unique_id"]
    
    try:
        # Initialize coordinator
        coordinator = MaxSmartCoordinator(hass, device_ip)
        
        # Perform initial data fetch to verify device connectivity
        await coordinator.async_config_entry_first_refresh()
        
        # Store coordinator in hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator
        
        # Forward setup to platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        _LOGGER.info("MaxSmart integration setup completed for device: %s", device_ip)
        return True
        
    except Exception as err:
        _LOGGER.error("Failed to setup MaxSmart integration for %s: %s", device_ip, err)
        raise ConfigEntryNotReady(f"Unable to connect to device {device_ip}: {err}")

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading MaxSmart integration for device: %s", entry.title)
    
    try:
        # Unload platforms
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        
        if unload_ok:
            # Get and shutdown coordinator
            coordinator: MaxSmartCoordinator = hass.data[DOMAIN][entry.entry_id]
            await coordinator.async_shutdown()
            
            # Remove from hass data
            hass.data[DOMAIN].pop(entry.entry_id)
            
            # Clean up domain data if no more entries
            if not hass.data[DOMAIN]:
                hass.data.pop(DOMAIN)
                
            _LOGGER.info("MaxSmart integration unloaded successfully")
        
        return unload_ok
        
    except Exception as err:
        _LOGGER.error("Error unloading MaxSmart integration: %s", err)
        return False

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)