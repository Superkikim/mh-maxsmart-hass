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
            
        _LOGGER.info("Checking %d MaxSmart config entries for robust migration", len(entries))
        
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
                    _LOGGER.info("Found serial match: %s (IP changed %s -> %s)", 
                               entry_serial, entry_ip, device.get("ip"))
                    return device
        
        # Priority 3: MAC Address comparison (hardware-based matching)
        try:
            # Get MAC for the entry's IP (may fail if device offline)
            entry_mac = await self._get_mac_for_ip(entry_ip)
            
            if entry_mac:
                for device in current_devices:
                    # Check both mac_address and pclmac fields
                    device_mac = device.get("mac_address") or device.get("pclmac")
                    
                    if device_mac and self._normalize_mac(entry_mac) == self._normalize_mac(device_mac):
                        _LOGGER.info("Found MAC match: %s (%s -> %s)", 
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
            
            # 🔑 Update config entry WITHOUT changing unique_id
            self.hass.config_entries.async_update_entry(
                entry,
                data=enhanced_data
                # Explicitly NOT setting unique_id = preserves original
            )
            
            result["status"] = "legacy_migrated"
            result["changes"] = self._calculate_changes(entry.data, enhanced_data)
            
            _LOGGER.info("Successfully migrated %s: preserved unique_id %s, method=%s", 
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
        
        # Generate best available unique identifier for reference only
        best_unique_id = self._generate_new_unique_id(device)
        
        # Determine identification method
        identification_method = self._determine_identification_method(device)
        
        # Build enhanced data structure
        enhanced_data = {
            # Preserve existing configuration
            "device_name": old_data.get("device_name", device.get("name", "MaxSmart Device")),
            "device_ip": device["ip"],  # Use current IP (may have changed)
            
            # 🔑 KEEP original unique_id to prevent device duplication
            "device_unique_id": original_unique_id,
            
            # Add enhanced identification as metadata
            "best_unique_id": best_unique_id,
            "identification_method": identification_method,
            
            # Hardware identifiers (enrichment)
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
            "original_unique_id": original_unique_id,
            "hardware_enhanced": True,
        }
        
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
            _LOGGER.info("PRESERVING existing port configuration: %d ports", existing_port_count)
            return existing_port_count
        
        # Method 2: Check if stored port count exists
        stored_count = old_data.get("port_count")
        if stored_count and isinstance(stored_count, int) and stored_count in [1, 6]:
            _LOGGER.info("Using stored port count: %d", stored_count)
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
        elif device.get("mac_address"):
            mac_clean = self._normalize_mac(device["mac_address"])
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

    def _is_already_migrated(self, entry: ConfigEntry) -> bool:
        """Check if config entry is already in enhanced format."""
        data = entry.data
        
        # Enhanced format has hardware fields OR migration flag
        has_hardware_fields = any(field in data for field in ["cpu_id", "mac_address", "hardware_enhanced"])
        has_enhanced_fields = "identification_method" in data
        
        return has_hardware_fields or has_enhanced_fields
        
    def _is_legacy_entry(self, entry: ConfigEntry) -> bool:
        """Check if config entry is in legacy format."""
        data = entry.data
        
        # Legacy format characteristics
        has_legacy_structure = (
            "device_ip" in data and 
            "device_name" in data and
            "device_unique_id" in data
        )
        
        # Not already enhanced
        not_enhanced = not self._is_already_migrated(entry)
        
        return has_legacy_structure and not_enhanced

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

    async def _query_device_directly(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """Query device directly at specific IP address."""
        try:
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
                if port_names and port_id - 1 < len(port_names) and port_names[port_id - 1]:
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
            
        _LOGGER.info("=== MaxSmart Robust Migration Summary ===")
        _LOGGER.info("Total entries: %d", summary["total_entries"])
        _LOGGER.info("Legacy entries found: %d", summary["legacy_entries"])
        _LOGGER.info("Successfully migrated: %d", summary["migrated_successfully"])
        _LOGGER.info("Already migrated: %d", summary["already_migrated"])
        
        if summary["migration_failed"] > 0:
            _LOGGER.warning("Migration failed: %d", summary["migration_failed"])
            
        # Log individual migration details
        for detail in summary["details"]:
            if detail["status"] == "legacy_migrated":
                _LOGGER.info("Migrated: %s (method: %s) - preserved unique_id: %s", 
                           detail["title"], detail.get("matching_method", "unknown"), detail["old_unique_id"])
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