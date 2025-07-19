# custom_components/maxsmart/__init__.py
"""The Max Hauri MaxSmart Power Devices integration with options support."""
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
    device_name = entry.data.get("device_name", "Unknown")
    device_ip = entry.data["device_ip"]
    
    _LOGGER.info("Setting up MaxSmart integration: %s (%s)", device_name, device_ip)
    
    try:
        # Initialize coordinator with config entry
        coordinator = MaxSmartCoordinator(hass, entry)
        
        # Perform initial data fetch with retries
        await coordinator.async_config_entry_first_refresh()
        
        # Store coordinator in hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator
        
        # Setup platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        # Setup options flow update listener
        entry.async_on_unload(entry.add_update_listener(async_update_options))
        
        _LOGGER.info("MaxSmart integration setup completed: %s (%s)", device_name, device_ip)
        return True
        
    except Exception as err:
        _LOGGER.error("Failed to setup MaxSmart integration %s (%s): %s", device_name, device_ip, err)
        raise ConfigEntryNotReady(f"Unable to connect to device {device_ip}: {err}") from err

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    device_name = entry.data.get("device_name", "Unknown")
    _LOGGER.info("Unloading MaxSmart integration: %s", device_name)
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Shutdown coordinator
        coordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_shutdown()
        
        # Remove from hass data
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # Clean up domain if no more entries
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
            
        _LOGGER.info("MaxSmart integration unloaded successfully: %s", device_name)
    else:
        _LOGGER.error("Failed to unload MaxSmart integration: %s", device_name)
    
    return unload_ok

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update (called when user changes names via options flow)."""
    device_name = entry.data.get("device_name", "Unknown")
    _LOGGER.info("Updating options for MaxSmart device: %s", device_name)
    
    try:
        # Get coordinator
        coordinator = hass.data[DOMAIN][entry.entry_id]
        
        # Reload coordinator with new config
        await coordinator.async_reload_from_config()
        
        # The options flow already handles the integration reload
        # so entities will be recreated with new names
        
        _LOGGER.info("Options updated successfully for MaxSmart device: %s", device_name)
        
    except Exception as err:
        _LOGGER.error("Failed to update options for MaxSmart device %s: %s", device_name, err)
        # Don't raise - let the reload handle any issues

async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entries to new format if needed."""
    version = config_entry.version
    
    _LOGGER.debug("Migrating MaxSmart config entry from version %s", version)
    
    # Currently version 1, no migration needed yet
    if version == 1:
        # No migration needed
        return True
        
    # Future migrations would go here
    # if version < 2:
    #     # Migrate from v1 to v2
    #     new_data = {**config_entry.data}
    #     # ... migration logic ...
    #     hass.config_entries.async_update_entry(
    #         config_entry, data=new_data, version=2
    #     )
    
    _LOGGER.info("Migration completed for MaxSmart config entry")
    return True

async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry."""
    device_name = entry.data.get("device_name", "Unknown")
    _LOGGER.info("Removing MaxSmart integration: %s", device_name)
    
    # Cleanup any persistent data if needed
    # (Currently not needed as we don't store persistent data)
    
    _LOGGER.info("MaxSmart integration removed: %s", device_name)