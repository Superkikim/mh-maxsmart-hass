# custom_components/maxsmart/migration.py
"""MaxSmart configuration migration system for seamless upgrades."""

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
    """Manages migration of MaxSmart config entries from legacy to enhanced format."""
    
    def __init__(self, hass: HomeAssistant):
        """Initialize migration manager."""
        self.hass = hass
        self._migration_cache: Dict[str, Dict[str, Any]] = {}
        
    async def check_and_migrate_entries(self) -> Dict[str, Any]:
        """
        Check for legacy config entries and migrate them to new format.
        
        Returns:
            Migration summary with details of what was migrated
        """
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
            
        _LOGGER.info("Checking %d MaxSmart config entries for migration", len(entries))
        
        # Discover current devices for mapping
        current_devices = await self._discover_current_devices()
        
        # Process each entry
        for entry in entries:
            result = await self._migrate_single_entry(entry, current_devices)
            migration_summary["details"].append(result)
            
            # Update counters
            if result["status"] == "legacy_migrated":
                migration_summary["migrated_successfully"] += 1
                migration_summary["legacy_entries"] += 1
            elif result["status"] == "migration_failed":
                migration_summary["migration_failed"] += 1
                migration_summary["legacy_entries"] += 1
            elif result["status"] == "already_migrated":
                migration_summary["already_migrated"] += 1
            elif result["status"] == "legacy_detected":
                migration_summary["legacy_entries"] += 1
                
        # Log migration summary
        self._log_migration_summary(migration_summary)
        
        return migration_summary
        
    async def _discover_current_devices(self) -> List[Dict[str, Any]]:
        """Discover current devices with enhanced identification."""
        try:
            _LOGGER.debug("Discovering current devices for migration mapping")
            devices = await MaxSmartDiscovery.discover_maxsmart(enhance_with_hardware_ids=True)
            _LOGGER.debug("Found %d devices for migration mapping", len(devices))
            return devices or []
        except Exception as err:
            _LOGGER.warning("Failed to discover devices for migration: %s", err)
            return []
            
    async def _migrate_single_entry(self, entry: ConfigEntry, current_devices: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Migrate a single config entry from legacy to enhanced format.
        
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
            "new_unique_id": None,
            "device_ip": entry.data.get("device_ip", "unknown"),
            "changes": {},
            "error": None
        }
        
        try:
            # Check if already migrated
            if self._is_already_migrated(entry):
                result["status"] = "already_migrated"
                _LOGGER.debug("Entry %s already migrated", entry.title)
                return result
                
            # Detect legacy format
            if not self._is_legacy_entry(entry):
                result["status"] = "not_legacy"
                return result
                
            result["status"] = "legacy_detected"
            _LOGGER.info("Migrating legacy entry: %s (%s)", entry.title, entry.data.get("device_ip"))
            
            # Find matching device
            matched_device = await self._find_matching_device(entry, current_devices)
            
            if not matched_device:
                result["status"] = "migration_failed"
                result["error"] = "Could not find matching device on network"
                _LOGGER.warning("Migration failed for %s: device not found", entry.title)
                return result
                
            # Build enhanced config data
            enhanced_data = await self._build_enhanced_config_data(entry, matched_device)
            
            # Update config entry
            self.hass.config_entries.async_update_entry(
                entry,
                data=enhanced_data,
                unique_id=enhanced_data["device_unique_id"]
            )
            
            result["status"] = "legacy_migrated"
            result["new_unique_id"] = enhanced_data["device_unique_id"]
            result["changes"] = self._calculate_changes(entry.data, enhanced_data)
            
            _LOGGER.info("Successfully migrated %s: %s -> %s", 
                        entry.title, entry.unique_id, enhanced_data["device_unique_id"])
            
        except Exception as err:
            result["status"] = "migration_failed" 
            result["error"] = str(err)
            _LOGGER.error("Failed to migrate entry %s: %s", entry.title, err)
            
        return result
        
    def _is_already_migrated(self, entry: ConfigEntry) -> bool:
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
        
    def _is_legacy_entry(self, entry: ConfigEntry) -> bool:
        """Check if config entry is in legacy format."""
        data = entry.data
        
        # Legacy format characteristics
        has_legacy_structure = (
            "device_ip" in data and 
            "device_name" in data and
            "device_unique_id" in data
        )
        
        # Legacy unique_id is typically the serial number directly
        legacy_id_pattern = (
            entry.unique_id and 
            not any(entry.unique_id.startswith(prefix) for prefix in ["cpu_", "mac_", "ip_"]) and
            len(entry.unique_id) > 5  # Serial numbers are typically longer
        )
        
        return has_legacy_structure and legacy_id_pattern
        
    async def _find_matching_device(self, entry: ConfigEntry, current_devices: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Find matching device using IP and serial number.
        
        Priority matching order:
        1. IP + Serial match
        2. IP match only (most reliable for static IPs)
        3. Serial match only (for DHCP environments)
        """
        entry_ip = entry.data.get("device_ip")
        entry_serial = entry.unique_id or entry.data.get("device_unique_id")
        
        if not entry_ip:
            return None
            
        _LOGGER.debug("Looking for device: IP=%s, Serial=%s", entry_ip, entry_serial)
        
        # Priority 1: IP + Serial match (best case)
        for device in current_devices:
            if (device.get("ip") == entry_ip and 
                device.get("sn") == entry_serial):
                _LOGGER.debug("Found exact match (IP+Serial): %s", entry_ip)
                return device
                
        # Priority 2: IP match only (very reliable for static IPs)
        for device in current_devices:
            if device.get("ip") == entry_ip:
                _LOGGER.debug("Found IP match: %s (serial may have changed)", entry_ip)
                return device
                
        # Priority 3: Serial match only (for devices that changed IP)
        if entry_serial:
            for device in current_devices:
                if device.get("sn") == entry_serial:
                    _LOGGER.debug("Found serial match: %s (IP changed %s -> %s)", 
                                entry_serial, entry_ip, device.get("ip"))
                    return device
                    
        # Priority 4: Try direct device query at stored IP
        try:
            _LOGGER.debug("Attempting direct device query at %s", entry_ip)
            device = await self._query_device_directly(entry_ip)
            if device:
                _LOGGER.debug("Found device via direct query: %s", entry_ip)
                return device
        except Exception as err:
            _LOGGER.debug("Direct query failed for %s: %s", entry_ip, err)
            
        return None
        
    async def _query_device_directly(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """Query device directly at specific IP address."""
        try:
            # Create temporary device for querying
            temp_device = MaxSmartDevice(ip_address)
            await temp_device.initialize_device()
            
            # Get hardware identifiers
            hw_ids = await temp_device.get_device_identifiers()
            
            # Try to get MAC via ARP
            mac_address = await temp_device.get_mac_address_via_arp()
            
            # Build device info similar to discovery
            device_info = {
                "ip": ip_address,
                "name": getattr(temp_device, 'name', ''),
                "sn": getattr(temp_device, 'sn', ''),
                "ver": getattr(temp_device, 'version', ''),
                "pname": getattr(temp_device, 'port_names', []),
                "cpuid": hw_ids.get("cpuid", ""),
                "pclmac": hw_ids.get("pclmac", ""),
                "mac_address": mac_address or hw_ids.get("pclmac", ""),
                "hw_ids": hw_ids,
            }
            
            await temp_device.close()
            return device_info
            
        except Exception:
            return None
            
    async def _build_enhanced_config_data(self, entry: ConfigEntry, device: Dict[str, Any]) -> Dict[str, Any]:
        """Build enhanced config data from legacy entry and discovered device."""
        old_data = entry.data.copy()
        
        # Determine best unique identifier
        device_unique_id = self._generate_new_unique_id(device)
        
        # Determine identification method
        identification_method = self._determine_identification_method(device)
        
        # Build enhanced data structure
        enhanced_data = {
            # Preserve existing configuration
            "device_name": old_data.get("device_name", device.get("name", "MaxSmart Device")),
            "device_ip": device["ip"],  # Use current IP (may have changed)
            
            # New identification system
            "device_unique_id": device_unique_id,
            "identification_method": identification_method,
            
            # Hardware identifiers
            "cpu_id": device.get("cpuid", ""),
            "mac_address": device.get("mac_address", ""),
            "udp_serial": device.get("sn", ""),
            "pclmac": device.get("pclmac", ""),
            
            # Device info
            "sw_version": device.get("ver", "Unknown"),
            "firmware_version": device.get("ver", "Unknown"),
            "port_count": self._determine_port_count(device, old_data),
            
            # Migration metadata
            "migrated_from_version": "1.0",
            "migration_timestamp": datetime.datetime.utcnow().isoformat(),
            "original_unique_id": entry.unique_id,
        }
        
        # Preserve port names from old configuration
        self._preserve_port_names(old_data, enhanced_data, device)
        
        return enhanced_data
        
    def _generate_new_unique_id(self, device: Dict[str, Any]) -> str:
        """Generate new unique ID using priority system."""
        # Priority: CPU ID -> MAC -> Serial -> IP
        if device.get("cpuid"):
            return f"cpu_{device['cpuid']}"
        elif device.get("mac_address"):
            mac_clean = device["mac_address"].replace(':', '').lower()
            return f"mac_{mac_clean}"
        elif device.get("sn"):
            return f"sn_{device['sn']}"
        else:
            ip_clean = device["ip"].replace('.', '_')
            return f"ip_{ip_clean}"
            
    def _determine_identification_method(self, device: Dict[str, Any]) -> str:
        """Determine which identification method was used."""
        if device.get("cpuid"):
            return "cpu_id"
        elif device.get("mac_address"):
            return "mac_address"
        elif device.get("sn"):
            return "udp_serial"
        else:
            return "ip_fallback"
            
    def _determine_port_count(self, device: Dict[str, Any], old_data: Dict[str, Any]) -> int:
        """Determine port count from device and legacy data."""
        # Check if port count was stored in legacy data
        for port_id in range(1, 7):
            if f"port_{port_id}_name" not in old_data:
                return port_id - 1 if port_id > 1 else 6
                
        # Fallback to device serial pattern
        serial = device.get("sn", "")
        if serial and len(serial) >= 4:
            try:
                port_char = serial[3]
                if port_char == '1':
                    return 1
                elif port_char == '6':
                    return 6
            except (IndexError, ValueError):
                pass
                
        return 6  # Default assumption
        
    def _preserve_port_names(self, old_data: Dict[str, Any], enhanced_data: Dict[str, Any], device: Dict[str, Any]) -> None:
        """Preserve port names from legacy configuration."""
        port_count = enhanced_data["port_count"]
        
        # Copy existing port names
        for port_id in range(1, port_count + 1):
            port_key = f"port_{port_id}_name"
            if port_key in old_data:
                enhanced_data[port_key] = old_data[port_key]
            else:
                # Use device port names as fallback
                port_names = device.get("pname", [])
                if port_id - 1 < len(port_names) and port_names[port_id - 1]:
                    enhanced_data[port_key] = port_names[port_id - 1]
                else:
                    enhanced_data[port_key] = f"Port {port_id}"
                    
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
        if new_data.get("cpu_id"):
            new_identifiers.append("CPU ID")
        if new_data.get("mac_address"):
            new_identifiers.append("MAC Address")
            
        if new_identifiers:
            changes["added_identifiers"] = new_identifiers
            
        changes["identification_method"] = new_data.get("identification_method")
        
        return changes
        
    def _log_migration_summary(self, summary: Dict[str, Any]) -> None:
        """Log migration summary."""
        if summary["total_entries"] == 0:
            return
            
        _LOGGER.info("=== MaxSmart Migration Summary ===")
        _LOGGER.info("Total entries: %d", summary["total_entries"])
        _LOGGER.info("Legacy entries found: %d", summary["legacy_entries"])
        _LOGGER.info("Successfully migrated: %d", summary["migrated_successfully"])
        _LOGGER.info("Already migrated: %d", summary["already_migrated"])
        
        if summary["migration_failed"] > 0:
            _LOGGER.warning("Migration failed: %d", summary["migration_failed"])
            
        # Log individual migration details
        for detail in summary["details"]:
            if detail["status"] == "legacy_migrated":
                _LOGGER.info("Migrated: %s (%s) -> %s", 
                           detail["title"], detail["old_unique_id"], detail["new_unique_id"])
            elif detail["status"] == "migration_failed":
                _LOGGER.warning("Failed: %s - %s", detail["title"], detail["error"])


async def async_migrate_config_entries(hass: HomeAssistant) -> Dict[str, Any]:
    """
    Main migration entry point - called during integration setup.
    
    Args:
        hass: Home Assistant instance
        
    Returns:
        Migration summary
    """
    _LOGGER.debug("Starting MaxSmart config entries migration check")
    
    migration_manager = MaxSmartMigrationManager(hass)
    summary = await migration_manager.check_and_migrate_entries()
    
    _LOGGER.debug("MaxSmart migration check completed")
    return summary