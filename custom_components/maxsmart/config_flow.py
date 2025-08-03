# custom_components/maxsmart/config_flow.py
"""Enhanced config flow with improved device identification and filtering."""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import DOMAIN
from .discovery import async_discover_devices, async_discover_device_by_ip

_LOGGER = logging.getLogger(__name__)

# Validation patterns
NAME_PATTERN = re.compile(r'^[\w\s\-\.]+$', re.UNICODE)
MAX_NAME_LENGTH = 50

class MaxSmartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for MaxSmart devices with enhanced identification."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> MaxSmartOptionsFlow:
        """Get the options flow for this handler."""
        return MaxSmartOptionsFlow(config_entry)

    def __init__(self):
        """Initialize config flow."""
        self._discovered_device: Optional[Dict[str, Any]] = None

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step with enhanced discovery and filtering."""
        errors: Dict[str, str] = {}

        if user_input is None:
            # Enhanced auto-discovery with filtering
            try:
                _LOGGER.debug("Starting enhanced MaxSmart device discovery")
                devices = await async_discover_devices(enhance_with_hardware=True)
                
                if devices:
                    # Filter out already configured devices
                    unconfigured_devices = []
                    
                    for device in devices:
                        device_id = self._get_device_unique_id(device)
                        if not self._is_device_configured_robust(device, device_id):
                            unconfigured_devices.append(device)
                        else:
                            _LOGGER.debug("Device already configured, skipping: %s (%s)", 
                                        device.get("name", "Unknown"), device.get("ip", "Unknown"))
                    
                    if unconfigured_devices:
                        # Create discovery flows for unconfigured devices only
                        discovery_count = 0
                        for device in unconfigured_devices:
                            self.hass.async_create_task(
                                self.hass.config_entries.flow.async_init(
                                    DOMAIN,
                                    context={"source": "discovery"},
                                    data=device
                                )
                            )
                            discovery_count += 1
                        
                        if discovery_count > 0:
                            return self.async_abort(
                                reason="devices_found",
                                description_placeholders={"count": str(discovery_count)}
                            )
                    else:
                        # All devices already configured
                        _LOGGER.info("All discovered devices are already configured")
                        return self.async_abort(reason="devices_configured")
                        
                # No devices found - show manual form
                _LOGGER.info("No unconfigured devices found, showing manual form")
                
            except Exception as err:
                _LOGGER.warning("Enhanced discovery failed: %s", err)
                errors["base"] = "discovery_failed"

        else:
            # Handle manual IP input
            ip_address = user_input[CONF_IP_ADDRESS].strip()
            
            # Validate IP format
            try:
                ipaddress.ip_address(ip_address)
            except ValueError:
                errors["ip_address"] = "invalid_ip"
            else:
                # Try to discover at specific IP with hardware enhancement
                try:
                    device = await async_discover_device_by_ip(ip_address, enhance_with_hardware=True)
                    if device:
                        device_id = self._get_device_unique_id(device)
                        # Check if already configured using robust method
                        if self._is_device_configured_robust(device, device_id):
                            return self.async_abort(reason="device_already_configured")
                        
                        self._discovered_device = device
                        return await self.async_step_customize_names()
                    else:
                        errors["ip_address"] = "no_device_found"
                except Exception as err:
                    _LOGGER.error("Manual discovery failed: %s", err)
                    errors["ip_address"] = "connection_error"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_IP_ADDRESS): str,
            }),
            errors=errors,
        )

    async def async_step_discovery(self, discovery_info: Dict[str, Any]) -> FlowResult:
        """Handle discovery from automatic discovery."""
        device_id = self._get_device_unique_id(discovery_info)
        device_name = discovery_info.get("name", "Unknown Device")
        device_ip = discovery_info.get("ip", "Unknown")
        
        if not device_id:
            return self.async_abort(reason="no_device")
            
        # Check if already configured using robust method
        if self._is_device_configured_robust(discovery_info, device_id):
            return self.async_abort(reason="device_already_configured")
            
        # Set unique ID to prevent duplicates
        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured()
        
        # Set as discovered device and go to naming
        self._discovered_device = discovery_info
        
        # Update flow title for the discovery card
        self.context["title_placeholders"] = {
            "name": device_name,
            "ip": device_ip
        }
        
        return await self.async_step_customize_names()

    async def async_step_customize_names(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle device and port name customization with enhanced device info."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Validate all names
            validation_errors = self._validate_names(user_input)
            if validation_errors:
                errors.update(validation_errors)
            else:
                # Create the config entry with enhanced data
                return await self._create_entry_from_names(user_input)

        # Determine port count and default names
        device = self._discovered_device
        port_count = self._get_port_count_from_device(device)
        device_name = device.get("name", "") or device["ip"]
        port_names = device.get("pname", [])

        # Build schema dynamically based on port count
        schema_dict = {
            vol.Required("device_name", default=device_name): str,
        }

        # Add port name fields
        for port_id in range(1, port_count + 1):
            default_name = (
                port_names[port_id - 1] if port_id - 1 < len(port_names) and port_names[port_id - 1]
                else f"Port {port_id}"
            )
            schema_dict[vol.Required(f"port_{port_id}_name", default=default_name)] = str

        # Enhanced device info with hardware identifiers
        device_info = self._format_device_info_for_display(device)

        return self.async_show_form(
            step_id="customize_names",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "device_info": device_info
            }
        )

    async def _create_entry_from_names(self, names: Dict[str, Any]) -> FlowResult:
        """Create config entry with enhanced device data including MAC address."""
        device = self._discovered_device
        device_id = self._get_device_unique_id(device)
        
        # Set unique ID to prevent duplicates
        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured()
        
        # Build enhanced entry data
        entry_data = {
            # Core identification
            "device_unique_id": device_id,
            "device_ip": device["ip"],
            "device_name": names["device_name"],
            "sw_version": device.get("ver", "Unknown"),
            
            # Hardware identifiers (new)
            "cpu_id": device.get("cpu_id", ""),
            "mac_address": device.get("mac_address", ""),
            "udp_serial": device.get("sn", ""),
            "identification_method": device.get("identification_method", "fallback"),
            
            # Device capabilities
            "firmware_version": device.get("ver", "Unknown"),
            "port_count": self._get_port_count_from_device(device),
        }
        
        # Add port names
        port_count = self._get_port_count_from_device(device)
        for port_id in range(1, port_count + 1):
            port_key = f"port_{port_id}_name"
            entry_data[port_key] = names[port_key]
        
        return self.async_create_entry(
            title=f"MaxSmart {names['device_name']}",
            data=entry_data,
        )

    def _get_device_unique_id(self, device: Dict[str, Any]) -> str:
        """Extract the best unique ID from enhanced device data."""
        # Priority order: CPU ID -> MAC -> UDP Serial -> IP
        if device.get("cpu_id"):
            return f"cpu_{device['cpu_id']}"
        elif device.get("mac_address"):
            mac_clean = device["mac_address"].replace(':', '').lower()
            return f"mac_{mac_clean}"
        elif device.get("sn") and self._is_serial_reliable(device["sn"]):
            return f"sn_{device['sn']}"
        else:
            ip_clean = device["ip"].replace('.', '_')
            return f"ip_{ip_clean}"

    def _get_port_count_from_device(self, device: Dict[str, Any]) -> int:
        """Determine port count from enhanced device data."""
        # Try multiple methods to determine port count
        
        # Method 1: From CPU ID pattern (if available)
        cpu_id = device.get("cpu_id", "")
        if cpu_id and len(cpu_id) >= 4:
            # Some CPU IDs might contain port info - this is device-specific
            pass
            
        # Method 2: From UDP serial pattern
        serial = device.get("sn", "")
        if serial and len(serial) >= 4:
            try:
                port_char = serial[3]
                if port_char == '1':
                    return 1  # Single port device
                elif port_char == '6':
                    return 6  # 6-port device
            except (IndexError, ValueError):
                pass
                
        # Method 3: From port names count
        port_names = device.get("pname", [])
        if port_names and isinstance(port_names, list):
            return len([name for name in port_names if name])
        elif port_names is None:
            # pname: None usually indicates single port device
            return 1
            
        # Default fallback
        return 6

    def _format_device_info_for_display(self, device: Dict[str, Any]) -> str:
        """Format enhanced device information for display."""
        lines = []
        
        # Basic info
        lines.append(f"Device: {device.get('name', 'Unknown')}")
        lines.append(f"IP: {device['ip']}")
        lines.append(f"Firmware: {device.get('ver', 'Unknown')}")
        lines.append(f"Ports: {self._get_port_count_from_device(device)}")
        
        # Hardware identifiers
        if device.get("cpu_id"):
            lines.append(f"CPU ID: {device['cpu_id'][:16]}...")
            
        if device.get("mac_address"):
            lines.append(f"MAC: {device['mac_address']}")
            
        if device.get("sn"):
            lines.append(f"Serial: {device['sn']}")
            
        # Identification method
        method = device.get("identification_method", "unknown")
        lines.append(f"ID Method: {method.upper()}")
        
        return "\n".join(lines)

    def _validate_names(self, names: Dict[str, Any]) -> Dict[str, str]:
        """Validate all provided names."""
        errors = {}
        used_names = set()

        for key, name in names.items():
            name = name.strip()
            
            # Check if empty
            if not name:
                errors[key] = "name_required"
                continue
                
            # Check length
            if len(name) > MAX_NAME_LENGTH:
                errors[key] = "name_too_long"
                continue
                
            # Check characters
            if not NAME_PATTERN.match(name):
                errors[key] = "invalid_characters"
                continue
                
            # Check for duplicates
            if name.lower() in used_names:
                errors[key] = "name_duplicate"
                continue
                
            used_names.add(name.lower())

        return errors

    def _is_serial_reliable(self, sn: str) -> bool:
        """Check if UDP serial number is reliable."""
        return (
            sn and 
            isinstance(sn, str) and 
            sn.strip() and 
            len(sn) > 3 and 
            all(ord(c) < 128 for c in sn) and 
            sn.isprintable()
        )

    def _is_device_configured_robust(self, device: Dict[str, Any], device_id: str) -> bool:
        """
        Check if device is already configured using multiple methods.
        
        Args:
            device: Device info from discovery
            device_id: Generated device ID
            
        Returns:
            True if device is already configured
        """
        # Method 1: Check by generated device_id
        if self._is_device_configured(device_id):
            return True
            
        # Method 2: Check by serial number (legacy entries)
        device_serial = device.get("sn")
        if device_serial:
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if (entry.unique_id == device_serial or 
                    entry.data.get("device_unique_id") == device_serial or
                    entry.data.get("udp_serial") == device_serial):
                    return True
        
        # Method 3: Check by IP address (devices that changed serial)
        device_ip = device.get("ip")
        if device_ip:
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if entry.data.get("device_ip") == device_ip:
                    return True
        
        # Method 4: Check by MAC address (if available)
        device_mac = device.get("mac_address") or device.get("pclmac")
        if device_mac:
            normalized_mac = self._normalize_mac(device_mac)
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                entry_mac = entry.data.get("mac_address") or entry.data.get("pclmac")
                if entry_mac and self._normalize_mac(entry_mac) == normalized_mac:
                    return True
        
        return False

    def _normalize_mac(self, mac_address: str) -> str:
        """Normalize MAC address for comparison."""
        if not mac_address:
            return ""
        return mac_address.replace(":", "").replace("-", "").lower()

    def _is_device_configured(self, device_id: str) -> bool:
        """Check if device is already configured using enhanced ID."""
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.data.get("device_unique_id") == device_id:
                return True
        return False


class MaxSmartOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for MaxSmart devices."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle options flow initialization."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Validate names
            validation_errors = self._validate_names(user_input)
            if validation_errors:
                errors.update(validation_errors)
            else:
                # Update config entry data
                new_data = {**self.config_entry.data}
                new_data.update(user_input)
                
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=new_data
                )
                
                # Reload the integration to apply new names
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                
                return self.async_create_entry(title="", data={})

        # Get current values
        current_data = self.config_entry.data
        port_count = current_data.get("port_count", 6)

        # Build schema with current values
        schema_dict = {
            vol.Required("device_name", default=current_data["device_name"]): str,
        }

        for port_id in range(1, port_count + 1):
            port_key = f"port_{port_id}_name"
            current_name = current_data.get(port_key, f"Port {port_id}")
            schema_dict[vol.Required(port_key, default=current_name)] = str

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    def _validate_names(self, names: Dict[str, Any]) -> Dict[str, str]:
        """Validate all provided names."""
        errors = {}
        used_names = set()

        for key, name in names.items():
            name = name.strip()
            
            if not name:
                errors[key] = "name_required"
                continue
                
            if len(name) > MAX_NAME_LENGTH:
                errors[key] = "name_too_long"
                continue
                
            if not NAME_PATTERN.match(name):
                errors[key] = "invalid_characters"
                continue
                
            if name.lower() in used_names:
                errors[key] = "name_duplicate"
                continue
                
            used_names.add(name.lower())

        return errors
