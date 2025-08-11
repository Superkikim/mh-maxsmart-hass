# custom_components/maxsmart/migration.py
"""Conservative MaxSmart migration with robust matching and port count preservation."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from maxsmart import MaxSmartDiscovery, MaxSmartDevice
from maxsmart.exceptions import DiscoveryError, ConnectionError as MaxSmartConnectionError

_LOGGER = logging.getLogger(__name__)

class MaxSmartMigrationManager:
    """Manages robust migration of MaxSmart config entries with MAC/Serial/IP matching."""
    
    def __init__(self, hass: HomeAssistant):
        """Initialize migration manager."""
        self.hass = hass
        
    async def check_and_migrate_entries(self) -> Dict[str, Any]:
        """Check for legacy config entries and migrate them robustly."""
        migration_summary = {
            "total_entries": 0,
            "legacy_entries": 0,
            "migrated_successfully": 0,
            "migration_failed": 0,
            "already_migrated": 0,
            "details": []
        }
        
        # Get all MaxSmart config entries
        entries = self.hass.config_entries.async_entries("maxsmart")
        migration_summary["total_entries"] = len(entries)
        
        if not entries:
            _LOGGER.debug("No MaxSmart entries found for migration")
            return migration_summary
            
        _LOGGER.debug("Checking %d MaxSmart config entries for robust migration", len(entries))
        
        # Discover current devices for mapping
        current_devices = await self._discover_current_devices()
        
        # Process each entry
        for entry in entries:
            result = await self._migrate_single_entry(entry, current_devices)
            migration_summary["details"].append(result)
            
            # Update counters (simplified)
            if result["status"] == "migrated_successfully":
                migration_summary["migrated_successfully"] += 1
            elif result["status"] == "migration_failed":
                migration_summary["migration_failed"] += 1
            elif result["status"] == "no_migration_needed":
                migration_summary["already_migrated"] += 1
                
        # Log migration summary
        self._log_migration_summary(migration_summary)
        
        return migration_summary

    async def _find_matching_device(self, entry: ConfigEntry, current_devices: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Find matching device using robust identification: Serial -> MAC -> IP.
        
        Args:
            entry: Config entry to match
            current_devices: List of currently discovered devices
            
        Returns:
            Matching device dict or None
        """
        entry_ip = entry.data.get("device_ip")
        entry_serial = entry.unique_id or entry.data.get("device_unique_id")
        
        _LOGGER.debug("Looking for device: IP=%s, Serial=%s", entry_ip, entry_serial)
        
        # Priority 1: Exact Serial + IP match (best case)
        for device in current_devices:
            if (device.get("sn") == entry_serial and device.get("ip") == entry_ip):
                _LOGGER.debug("Found exact match (Serial+IP): %s", entry_ip)
                return device
        
        # Priority 2: Serial match only (IP may have changed via DHCP)
        if entry_serial:
            for device in current_devices:
                if device.get("sn") == entry_serial:
                    _LOGGER.debug("Found serial match: %s (IP changed %s -> %s)",
                               entry_serial, entry_ip, device.get("ip"))
                    return device
        
        # Priority 3: MAC Address comparison (hardware-based matching)
        try:
            # Get MAC for the entry's IP (may fail if device offline)
            entry_mac = await self._get_mac_for_ip(entry_ip)
            
            if entry_mac:
                for device in current_devices:
                    # Use only "mac" field from maxsmart 2.0.5 format
                    device_mac = device.get("mac")

                    if device_mac and self._normalize_mac(entry_mac) == self._normalize_mac(device_mac):
                        _LOGGER.debug("Found MAC match: %s (%s -> %s)",
                                   entry_mac, entry_ip, device.get("ip"))
                        return device
                        
        except Exception as e:
            _LOGGER.debug("MAC comparison failed for %s: %s", entry_ip, e)
        
        # Priority 4: IP match only (fallback, least reliable)
        for device in current_devices:
            if device.get("ip") == entry_ip:
                _LOGGER.debug("Found IP match only: %s (serial/MAC unavailable)", entry_ip)
                return device
        
        # Priority 5: Try direct device query at stored IP
        try:
            _LOGGER.debug("Attempting direct device query at %s", entry_ip)
            device = await self._query_device_directly(entry_ip)
            if device:
                _LOGGER.debug("Found device via direct query: %s", entry_ip)
                return device
        except Exception as err:
            _LOGGER.debug("Direct query failed for %s: %s", entry_ip, err)
            
        return None

    async def _get_mac_for_ip(self, ip_address: str) -> Optional[str]:
        """Get MAC address for IP using getmac (already available via maxsmart)."""
        try:
            from getmac import get_mac_address
            mac = get_mac_address(ip=ip_address)
            return mac
        except Exception as e:
            _LOGGER.debug("Failed to get MAC for %s: %s", ip_address, e)
            return None

    async def _cleanup_obsolete_entities(self, entry: ConfigEntry, enhanced_data: Dict[str, Any]) -> None:
        """
        Clean up obsolete entities for 1-port devices that were incorrectly configured with master.
        
        Hardware doesn't change! A 1-port device should NEVER have master entities.
        """
        try:
            detected_port_count = enhanced_data.get("port_count", 6)
            device_unique_id = enhanced_data["device_unique_id"]
            
            # ONLY clean up for 1-port devices that have master entities
            if detected_port_count != 1:
                _LOGGER.debug("Device %s has %d ports, no cleanup needed", entry.title, detected_port_count)
                return
            
            _LOGGER.debug("Device %s is 1-port, checking for incorrect master entities to remove", entry.title)
            
            # Get entity registry (correct import)
            from homeassistant.helpers import entity_registry as er
            entity_registry = er.async_get(self.hass)
            
            entities_to_remove = []
            
            # Remove master switch (port 0) - 1-port devices shouldn't have master
            master_switch_id = f"{device_unique_id}_0"
            master_entity = entity_registry.async_get_entity_id("switch", "maxsmart", master_switch_id)
            if master_entity:
                entities_to_remove.append(("switch", master_entity, "incorrect master switch"))
            
            # Remove total power sensor (port 0) - 1-port devices shouldn't have total power
            total_power_id = f"{device_unique_id}_0_power"
            total_entity = entity_registry.async_get_entity_id("sensor", "maxsmart", total_power_id)
            if total_entity:
                entities_to_remove.append(("sensor", total_entity, "incorrect total power sensor"))
            
            # Remove any incorrect port entities beyond port 1
            for port_id in range(2, 7):  # 1-port device should only have port 1
                # Remove switch
                port_switch_id = f"{device_unique_id}_{port_id}"
                port_switch_entity = entity_registry.async_get_entity_id("switch", "maxsmart", port_switch_id)
                if port_switch_entity:
                    entities_to_remove.append(("switch", port_switch_entity, f"incorrect port {port_id} switch"))
                
                # Remove power sensor
                port_power_id = f"{device_unique_id}_{port_id}_power"
                port_power_entity = entity_registry.async_get_entity_id("sensor", "maxsmart", port_power_id)
                if port_power_entity:
                    entities_to_remove.append(("sensor", port_power_entity, f"incorrect port {port_id} power sensor"))
            
            # Actually remove the incorrect entities
            for domain, entity_id, description in entities_to_remove:
                try:
                    entity_registry.async_remove(entity_id)
                    _LOGGER.debug("Removed %s: %s", description, entity_id)
                except Exception as e:
                    _LOGGER.warning("Failed to remove entity %s: %s", entity_id, e)
            
            if entities_to_remove:
                _LOGGER.debug("Cleaned up %d incorrect entities for 1-port device %s", len(entities_to_remove), entry.title)
            else:
                _LOGGER.debug("No incorrect entities found for 1-port device %s", entry.title)
                
        except Exception as e:
            _LOGGER.warning("Error during entity cleanup for %s: %s", entry.title, e)

    def _normalize_mac(self, mac_address: str) -> str:
        """Normalize MAC address for comparison."""
        if not mac_address:
            return ""
        # Remove separators and convert to lowercase for comparison
        return mac_address.replace(":", "").replace("-", "").lower()

    async def _migrate_single_entry(self, entry: ConfigEntry, current_devices: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Migrate a single config entry robustly, preserving unique_id.
        
        Args:
            entry: Config entry to migrate
            current_devices: List of currently discovered devices
            
        Returns:
            Migration result dictionary
        """
        result = {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "status": "unknown",
            "old_unique_id": entry.unique_id,
            "new_unique_id": entry.unique_id,  # Will preserve original
            "device_ip": entry.data.get("device_ip", "unknown"),
            "changes": {},
            "error": None,
            "matching_method": None
        }
        
        try:
            # Simple check: does entry need migration?
            if not self._needs_migration(entry):
                result["status"] = "no_migration_needed"
                _LOGGER.debug("Entry %s format is correct - no migration needed", entry.title)
                return result

            result["status"] = "migration_needed"
            _LOGGER.debug("Migrating entry: %s (%s)", entry.title, entry.data.get("device_ip", "unknown"))
            
            # Find matching device using robust matching
            matched_device = await self._find_matching_device(entry, current_devices)
            
            if not matched_device:
                result["status"] = "migration_failed"
                result["error"] = "Could not find matching device using Serial/MAC/IP"
                _LOGGER.warning("Migration failed for %s: device not found", entry.title)
                return result
            
            # Determine matching method used
            entry_serial = entry.unique_id
            if matched_device.get("sn") == entry_serial:
                result["matching_method"] = "serial"
            elif entry.data.get("device_ip") != matched_device.get("ip"):
                result["matching_method"] = "mac_or_fallback"
            else:
                result["matching_method"] = "ip"
                
            # Build enhanced config data (PRESERVING unique_id)
            enhanced_data = await self._build_enhanced_config_data(entry, matched_device)
            
            # 🔑 Clean up obsolete entities if port count changed
            await self._cleanup_obsolete_entities(entry, enhanced_data)
            
            # 🔑 Update config entry WITHOUT changing unique_id
            self.hass.config_entries.async_update_entry(
                entry,
                data=enhanced_data
                # Explicitly NOT setting unique_id = preserves original
            )
            
            result["status"] = "migrated_successfully"
            result["changes"] = self._calculate_changes(entry.data, enhanced_data)
            
            _LOGGER.debug("Successfully migrated %s: preserved unique_id %s, method=%s",
                        entry.title, entry.unique_id, result["matching_method"])
            
        except Exception as err:
            result["status"] = "migration_failed" 
            result["error"] = str(err)
            _LOGGER.error("Failed to migrate entry %s: %s", entry.title, err)
            
        return result

    async def _build_enhanced_config_data(self, entry: ConfigEntry, device: Dict[str, Any]) -> Dict[str, Any]:
        """Build enhanced config data while PRESERVING original unique_id."""
        old_data = entry.data.copy()
        
        # 🔑 PRESERVE original unique_id - this is crucial to prevent duplication
        original_unique_id = entry.unique_id or old_data.get("device_unique_id", "")
        
        # No need for complex identification logic in 2.0.5
        
        # Build clean enhanced data structure (maxsmart 2.0.5 format)
        enhanced_data = {
            # 🔑 PRESERVE original unique_id to prevent device duplication
            "device_unique_id": original_unique_id,

            # User configuration (preserve existing)
            "device_name": old_data.get("device_name", device.get("name", "MaxSmart Device")),

            # Essential maxsmart 2.0.5 data (clean format)
            "sn": device.get("sn", ""),
            "name": device.get("name", ""),
            "pname": device.get("pname", []),
            "device_ip": device["ip"],  # Use current IP (may have changed)
            "ver": device.get("ver", "Unknown"),
            "cpuid": device.get("cpuid", ""),
            "mac": device.get("mac", ""),
            "server": device.get("server", ""),

            # Device configuration
            "port_count": self._determine_port_count(device, old_data),

            # No migration metadata needed - keep it simple
        }

        # DEBUG: Log what we extracted from device
        _LOGGER.debug("🔧 MIGRATION BUILD: Device data = %s", device)
        _LOGGER.debug("🔧 MIGRATION BUILD: Extracted MAC = '%s' from device.get('mac')", device.get("mac", ""))
        _LOGGER.debug("🔧 MIGRATION BUILD: Enhanced data MAC = '%s'", enhanced_data.get("mac", ""))
        
        # Preserve port names from old configuration
        self._preserve_port_names(old_data, enhanced_data, device)
        
        return enhanced_data

    def _determine_port_count(self, device: Dict[str, Any], old_data: Dict[str, Any]) -> int:
        """
        Determine port count by PRESERVING existing configuration.
        Migration should not change working configurations!
        """
        
        # Method 1: Count existing port names in old_data (MOST RELIABLE)
        # If the device was configured with N ports, keep N ports!
        existing_port_count = 0
        for port_id in range(1, 7):
            port_key = f"port_{port_id}_name"
            if port_key in old_data:
                existing_port_count = port_id
        
        if existing_port_count > 0:
            _LOGGER.debug("PRESERVING existing port configuration: %d ports", existing_port_count)
            return existing_port_count
        
        # Method 2: Check if stored port count exists
        stored_count = old_data.get("port_count")
        if stored_count and isinstance(stored_count, int) and stored_count in [1, 6]:
            _LOGGER.debug("Using stored port count: %d", stored_count)
            return stored_count
            
        # Method 3: Analyze old entity structure if available
        # This is a fallback for cases where port names weren't stored properly
        
        # If we reach here, the old config was incomplete
        # Use device info as last resort, but this shouldn't happen in normal migration
        _LOGGER.warning("Old configuration incomplete, analyzing device info as fallback")
        
        # Device serial pattern analysis (fallback only)
        serial = device.get("sn", "")
        if serial and len(serial) >= 4:
            try:
                port_char = serial[3]
                if port_char == '1':
                    _LOGGER.debug("Device serial suggests 1-port device: %s", serial)
                    return 1
                elif port_char == '6':
                    _LOGGER.debug("Device serial suggests 6-port device: %s", serial)
                    return 6
            except (IndexError, ValueError):
                pass
        
        # Device pname analysis (fallback)
        port_names = device.get("pname")
        if port_names is None:
            _LOGGER.debug("Device has pname=None, assuming 1-port device")
            return 1
        elif isinstance(port_names, list):
            valid_names = [name for name in port_names if name and name.strip()]
            if valid_names:
                _LOGGER.debug("Device provides %d port names", len(valid_names))
                return len(valid_names)
                
        # Conservative fallback
        _LOGGER.warning("Could not determine port count reliably, defaulting to 6 ports")
        return 6

    def _generate_new_unique_id(self, device: Dict[str, Any]) -> str:
        """Generate new unique ID using priority system (for reference only)."""
        if device.get("cpuid"):
            return f"cpu_{device['cpuid']}"
        elif device.get("mac"):  # Fixed: use "mac" key from discovery
            mac_clean = self._normalize_mac(device["mac"])
            return f"mac_{mac_clean}"
        elif device.get("sn"):
            return f"sn_{device['sn']}"
        else:
            ip_clean = device["ip"].replace('.', '_')
            return f"ip_{ip_clean}"
            
    def _determine_identification_method(self, device: Dict[str, Any]) -> str:
        """Determine which identification method was used."""
        if device.get("cpuid"):
            return "cpuid"
        elif device.get("mac"):
            return "mac"
        elif device.get("sn"):
            return "sn"
        else:
            return "ip_fallback"

    def _needs_migration(self, entry: ConfigEntry) -> bool:
        """Check if config entry needs migration - simple format check."""
        data = entry.data

        # Expected 2025.8.2 format: device_ip, sn, mac, cpuid, ver, etc.
        required_fields = ["device_ip", "device_unique_id", "device_name"]
        expected_fields = ["sn", "mac", "cpuid", "ver"]

        # Check required fields
        for field in required_fields:
            if field not in data:
                _LOGGER.debug("Entry needs migration: missing required field '%s'", field)
                return True

        # Check expected 2025.8.2 fields
        missing_expected = [field for field in expected_fields if field not in data]
        if missing_expected:
            _LOGGER.debug("Entry needs migration: missing expected fields %s", missing_expected)
            return True

        # Check for obsolete 2025.7.1 fields that need renaming
        obsolete_fields = ["udp_serial", "cpu_id", "mac_address"]
        has_obsolete = any(field in data for field in obsolete_fields)
        if has_obsolete:
            _LOGGER.debug("Entry needs migration: has obsolete fields %s",
                         [field for field in obsolete_fields if field in data])
            return True

        _LOGGER.debug("Entry format is correct - no migration needed")
        return False
        
    # Supprimé - plus besoin de cette fonction complexe

    async def _discover_current_devices(self) -> List[Dict[str, Any]]:
        """Discover current devices with enhanced identification."""
        try:
            _LOGGER.debug("🔍 MIGRATION DISCOVERY: Starting device discovery for migration")
            # maxsmart 2.0.5+ always enhances with hardware IDs - no parameter needed
            devices = await MaxSmartDiscovery.discover_maxsmart()
            _LOGGER.debug("🔍 MIGRATION DISCOVERY: Found %d devices", len(devices))

            # DEBUG: Log device count only
            if devices:
                _LOGGER.debug("🔍 MIGRATION DISCOVERY: Found devices: %s",
                             [f"{d.get('name', 'Unknown')}@{d.get('ip', 'Unknown')}" for d in devices[:3]] +
                             (["..."] if len(devices) > 3 else []))

            return devices or []
        except Exception as err:
            _LOGGER.warning("Failed to discover devices for migration: %s", err)
            return []

    async def _query_device_directly(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """Query device directly at specific IP address."""
        try:
            # Try discovery first to get protocol info for maxsmart 2.1.0
            from .discovery import async_discover_device_by_ip
            device_info = await async_discover_device_by_ip(ip_address, enhance_with_hardware=True)

            protocol = None
            sn = None
            if device_info:
                protocol = device_info.get('protocol')
                sn = device_info.get('sn')

            # Create device with appropriate parameters
            if protocol and sn:
                temp_device = MaxSmartDevice(ip_address, protocol=protocol, sn=sn)
            elif protocol:
                temp_device = MaxSmartDevice(ip_address, protocol=protocol)
            else:
                temp_device = MaxSmartDevice(ip_address)

            await temp_device.initialize_device()

            # Get hardware identifiers
            hw_ids = await temp_device.get_device_identifiers()

            # Try to get MAC via ARP
            mac_address = await temp_device.get_mac_address_via_arp()

            # Build device info in maxsmart 2.0.5 format
            device_info = {
                "ip": ip_address,
                "name": getattr(temp_device, 'name', ''),
                "sn": getattr(temp_device, 'sn', ''),
                "ver": getattr(temp_device, 'version', ''),
                "pname": getattr(temp_device, 'port_names', []),
                "cpuid": hw_ids.get("cpuid", ""),
                "mac": mac_address,  # Clean MAC only
                "server": "",  # Not available via direct query
            }

            await temp_device.close()
            return device_info

        except Exception:
            return None
        
    def _preserve_port_names(self, old_data: Dict[str, Any], enhanced_data: Dict[str, Any], device: Dict[str, Any]) -> None:
        """Preserve port names from legacy configuration with smart port logic."""
        port_count = enhanced_data["port_count"]
        
        _LOGGER.debug("Preserving port names for %d-port device", port_count)
        
        # Copy existing port names (PRESERVE existing configuration)
        for port_id in range(1, port_count + 1):
            port_key = f"port_{port_id}_name"
            if port_key in old_data:
                enhanced_data[port_key] = old_data[port_key]
                _LOGGER.debug("Preserved existing port name: %s = %s", port_key, old_data[port_key])
            else:
                # Use device port names as fallback
                port_names = device.get("pname", [])
                if port_names and port_id - 1 < len(port_names) and port_names[port_id - 1]:
                    enhanced_data[port_key] = port_names[port_id - 1]
                    _LOGGER.debug("Using device port name: %s = %s", port_key, port_names[port_id - 1])
                else:
                    enhanced_data[port_key] = f"Port {port_id}"
                    _LOGGER.debug("Using default port name: %s = Port %d", port_key, port_id)
        
        # 🎯 IMPORTANT: Do NOT preserve master/total entities for 1-port devices
        # The new entity factory logic will handle this automatically
        # 1-port devices should not have master switches or total power sensors
        
        if port_count == 1:
            _LOGGER.debug("1-port device detected: Entity factory will create NO master switch or total power sensor")
        else:
            _LOGGER.debug("%d-port device detected: Entity factory will create master switch + total power sensor", port_count)
                    
    def _calculate_changes(self, old_data: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate what changed during migration."""
        changes = {}
        
        # Check IP change
        if old_data.get("device_ip") != new_data.get("device_ip"):
            changes["ip_changed"] = {
                "from": old_data.get("device_ip"),
                "to": new_data.get("device_ip")
            }
            
        # Check if new hardware identifiers were added
        new_identifiers = []
        if new_data.get("cpuid"):
            new_identifiers.append("CPU ID")
        if new_data.get("mac"):
            new_identifiers.append("MAC Address")

        if new_identifiers:
            changes["added_identifiers"] = new_identifiers
            
        changes["identification_method"] = new_data.get("identification_method")
        
        return changes
        
    def _log_migration_summary(self, summary: Dict[str, Any]) -> None:
        """Log migration summary."""
        if summary["total_entries"] == 0:
            return
            
        _LOGGER.info("=== MaxSmart Robust Migration Summary ===")
        _LOGGER.info("Total entries: %d", summary["total_entries"])
        _LOGGER.info("Legacy entries found: %d", summary["legacy_entries"])
        _LOGGER.info("Successfully migrated: %d", summary["migrated_successfully"])
        _LOGGER.info("Already migrated: %d", summary["already_migrated"])
        
        if summary["migration_failed"] > 0:
            _LOGGER.warning("Migration failed: %d", summary["migration_failed"])
            
        # Log individual migration details with port info
        for detail in summary["details"]:
            if detail["status"] == "legacy_migrated":
                # Get port count info if available
                port_info = ""
                try:
                    entries = self.hass.config_entries.async_entries("maxsmart")
                    for entry in entries:
                        if entry.entry_id == detail["entry_id"]:
                            port_count = entry.data.get("port_count", "unknown")
                            port_info = f" ({port_count}-port)"
                            break
                except:
                    pass
                    
                _LOGGER.debug("Migrated: %s (method: %s)%s - preserved unique_id: %s",
                           detail["title"], detail.get("matching_method", "unknown"),
                           port_info, detail["old_unique_id"])
            elif detail["status"] == "migration_failed":
                _LOGGER.warning("Failed: %s - %s", detail["title"], detail["error"])


async def async_migrate_config_entries(hass: HomeAssistant) -> Dict[str, Any]:
    """
    Main migration entry point with robust device matching.
    
    Args:
        hass: Home Assistant instance
        
    Returns:
        Migration summary
    """
    _LOGGER.debug("Starting MaxSmart robust migration check")
    
    migration_manager = MaxSmartMigrationManager(hass)
    summary = await migration_manager.check_and_migrate_entries()
    
    _LOGGER.debug("MaxSmart robust migration check completed")
    return summary