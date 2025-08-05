# custom_components/maxsmart/__init__.py
"""The Max Hauri MaxSmart Power Devices integration with migration support."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import MaxSmartCoordinator
from .migration import async_migrate_config_entries

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MaxSmart from a config entry with migration support."""
    device_name = entry.data.get("device_name", "Unknown")
    device_ip = entry.data["device_ip"]
    
    _LOGGER.info("Setting up MaxSmart integration: %s (%s)", device_name, device_ip)
    
    # Check for and perform migration ONLY ONCE for all entries
    if not hass.data.get(DOMAIN, {}).get('_migration_checked', False):
        try:
            _LOGGER.warning("🔄 MIGRATION: Performing one-time MaxSmart migration check")
            migration_summary = await async_migrate_config_entries(hass)
            _LOGGER.warning("🔄 MIGRATION: Migration completed with summary: %s", migration_summary)
            
            # Mark migration as completed and store summary
            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN]['_migration_checked'] = True
            hass.data[DOMAIN]['_last_migration_summary'] = migration_summary
            
            # Log migration results and show notification
            if migration_summary["migrated_successfully"] > 0:
                _LOGGER.info("Successfully migrated %d MaxSmart config entries", 
                           migration_summary["migrated_successfully"])
                
                # Show notification popup for successful migration using service call
                try:
                    await hass.services.async_call(
                        "persistent_notification", 
                        "create",
                        {
                            "title": "MaxSmart Migration Complete",
                            "message": f"{migration_summary['migrated_successfully']} MaxSmart devices have been migrated. "
                                      f"You can customize device and port names by clicking the gear icon of each device.",
                            "notification_id": "maxsmart_migration_success"
                        }
                    )
                    _LOGGER.info("Migration notification popup displayed successfully")
                except Exception as err:
                    _LOGGER.warning("Failed to display migration notification: %s", err)
                
            elif migration_summary["migration_failed"] > 0:
                _LOGGER.warning("Failed to migrate %d MaxSmart config entries - continuing with legacy format", 
                              migration_summary["migration_failed"])
                
        except Exception as err:
            _LOGGER.warning("Error during MaxSmart migration check: %s - continuing with legacy format", err)
            # Mark as checked to prevent repeated attempts
            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN]['_migration_checked'] = True
            hass.data[DOMAIN]['_last_migration_summary'] = {
                "migrated_successfully": 0,
                "migration_failed": 0,
                "total_entries": 0,
                "error": str(err)
            }
    
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
        
        # Log hardware information if available
        hw_info = _format_hardware_info(entry.data)
        _LOGGER.info("MaxSmart integration setup completed: %s (%s)%s", device_name, device_ip, hw_info)
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
        
        # Clean up domain if no more entries (but keep migration data)
        remaining_keys = [k for k in hass.data[DOMAIN].keys() if not k.startswith('_')]
        if not remaining_keys:
            # Keep migration metadata but clean up device entries
            migration_data = {
                k: v for k, v in hass.data[DOMAIN].items() 
                if k.startswith('_')
            }
            hass.data[DOMAIN] = migration_data
            
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
        
        _LOGGER.info("Options updated successfully for MaxSmart device: %s", device_name)
        
    except Exception as err:
        _LOGGER.error("Failed to update options for MaxSmart device %s: %s", device_name, err)

async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entries to new format if needed."""
    version = config_entry.version
    
    _LOGGER.debug("Checking MaxSmart config entry migration from version %s", version)
    
    if version == 1:
        # Check if this is actually a legacy entry that needs data migration
        if not _is_enhanced_format(config_entry):
            _LOGGER.info("Legacy config entry detected, will be migrated during setup")
            # The actual migration happens in async_setup_entry
            # This just ensures the version is correct
        return True
        
    # Future version migrations would go here
    # if version < 2:
    #     # Migrate from v1 to v2
    #     new_data = {**config_entry.data}
    #     # ... migration logic ...
    #     hass.config_entries.async_update_entry(
    #         config_entry, data=new_data, version=2
    #     )
    
    _LOGGER.debug("Config entry migration check completed")
    return True

async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry."""
    device_name = entry.data.get("device_name", "Unknown")
    _LOGGER.info("Removing MaxSmart integration: %s", device_name)
    
    # Cleanup any persistent data if needed
    # (Currently not needed as we don't store persistent data)
    
    _LOGGER.info("MaxSmart integration removed: %s", device_name)

def _is_enhanced_format(entry: ConfigEntry) -> bool:
    """Check if config entry is already in enhanced format."""
    data = entry.data
    
    # Enhanced format has these fields
    required_enhanced_fields = ["device_unique_id", "identification_method"]
    has_enhanced_fields = all(field in data for field in required_enhanced_fields)
    
    # Check if unique_id follows new pattern
    new_id_pattern = entry.unique_id and any(
        entry.unique_id.startswith(prefix) for prefix in ["cpu_", "mac_", "ip_"]
    )
    
    return has_enhanced_fields and new_id_pattern

def _format_hardware_info(data: dict) -> str:
    """Format hardware information for logging."""
    hw_parts = []
    
    identification_method = data.get("identification_method", "")
    if identification_method and identification_method != "fallback":
        hw_parts.append(f"ID: {identification_method.replace('_', ' ').title()}")
        
    cpu_id = data.get("cpu_id", "")
    if cpu_id:
        hw_parts.append(f"CPU: {cpu_id[:8]}...")
        
    mac_address = data.get("mac_address", "")
    if mac_address:
        hw_parts.append(f"MAC: {mac_address}")
        
    return f" [{', '.join(hw_parts)}]" if hw_parts else ""