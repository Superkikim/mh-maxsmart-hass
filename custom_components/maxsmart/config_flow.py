# custom_components/maxsmart/config_flow.py
"""Enhanced config flow with IP management in options and improved device identification."""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.data_entry_flow import FlowResult

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
        # config_entry is automatically provided by Home Assistant to the OptionsFlow
        return MaxSmartOptionsFlow()

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
                        _LOGGER.debug("All discovered devices are already configured")
                        return self.async_abort(reason="devices_configured")
                        
                # No devices found - show manual form
                _LOGGER.debug("No unconfigured devices found, showing manual form")
                
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
        firmware_version = device.get("ver", "Unknown")
        _LOGGER.debug("CONFIG_FLOW: Device data from discovery: %s", device)
        _LOGGER.debug("CONFIG_FLOW: Firmware version extracted: %s", firmware_version)
        entry_data = {
            # Core identification
            "device_unique_id": device_id,
            "device_ip": device["ip"],
            "device_name": names["device_name"],
            "sw_version": firmware_version,  # Used by device_info

            # Hardware identifiers (new)
            "cpu_id": device.get("cpu_id", ""),
            "mac_address": device.get("mac", ""),  # Fixed: use "mac" key from discovery
            "udp_serial": device.get("sn", ""),
            "identification_method": device.get("identification_method", "fallback"),

            # Device capabilities
            "firmware_version": firmware_version,  # Duplicate for backward compatibility
            "port_count": self._get_port_count_from_device(device),
        }
        
        # Add port names
        port_count = self._get_port_count_from_device(device)
        for port_id in range(1, port_count + 1):
            port_key = f"port_{port_id}_name"
            entry_data[port_key] = names[port_key]
        
        _LOGGER.debug("CONFIG_FLOW: Final entry data: %s", entry_data)
        return self.async_create_entry(
            title=f"MaxSmart {names['device_name']}",
            data=entry_data,
        )

    def _get_device_unique_id(self, device: Dict[str, Any]) -> str:
        """Extract the best unique ID from enhanced device data."""
        # 2025.8.1: Back to original priority order: Serial -> MAC -> CPU ID -> IP
        if device.get("sn") and self._is_serial_reliable(device["sn"]):
            return device["sn"]  # Use serial directly (no prefix)
        elif device.get("mac"):  # Fixed: use "mac" key from discovery
            mac_clean = device["mac"].replace(':', '').lower()
            return f"mac_{mac_clean}"
        elif device.get("cpuid"):
            return f"cpu_{device['cpuid']}"
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
            
        if device.get("mac"):  # Fixed: use "mac" key from discovery
            lines.append(f"MAC: {device['mac']}")
            
        if device.get("sn"):
            lines.append(f"Serial: {device['sn']}")

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
        device_mac = device.get("mac") or device.get("pclmac")  # Fixed: use "mac" key from discovery
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
    """Handle options flow for MaxSmart devices with IP management."""

    def __init__(self) -> None:
        """Initialize options flow."""

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle options flow with IP address management at the top."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Validate IP address first
            ip_address = user_input["device_ip"].strip()
            try:
                ipaddress.ip_address(ip_address)
            except ValueError:
                errors["device_ip"] = "invalid_ip"
            
            # Validate names
            name_validation_errors = self._validate_names(user_input)
            if name_validation_errors:
                errors.update(name_validation_errors)
            
            if not errors:
                # Check if IP changed
                old_ip = self.config_entry.data.get("device_ip")
                new_ip = ip_address
                ip_changed = old_ip != new_ip

                # Test new IP if it changed
                if ip_changed:
                    _LOGGER.debug("Testing connection to new IP %s for %s", new_ip, self.config_entry.data["device_name"])
                    connection_test = await self._test_ip_connection(new_ip)

                    if not connection_test:
                        # IP doesn't respond - store data and ask for confirmation
                        self._pending_user_input = user_input
                        self._pending_new_ip = new_ip
                        return await self.async_step_confirm_ip_change()

                # IP test passed or no IP change - process normally
                if ip_changed:
                    return await self._process_ip_change(user_input)
                else:
                    # No IP change - just update other data
                    new_data = {**self.config_entry.data}
                    new_data.update(user_input)

                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data=new_data
                    )

                    # Update entity names if port names changed
                    await self._update_entity_names_if_changed(new_data)

                    # Reload the integration to apply changes
                    await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                
                return self.async_create_entry(title="", data={})

        # Get current values
        current_data = self.config_entry.data
        port_count = current_data.get("port_count", 6)
        current_ip = current_data.get("device_ip", "")
        current_device_name = current_data.get("device_name", "")

        # Build schema with IP address at the top (most important)
        schema_dict = {
            vol.Required("device_ip", default=current_ip): str,
            vol.Required("device_name", default=current_device_name): str,
        }

        # Add port name fields
        for port_id in range(1, port_count + 1):
            port_key = f"port_{port_id}_name"
            current_name = current_data.get(port_key, f"Port {port_id}")
            schema_dict[vol.Required(port_key, default=current_name)] = str

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    def _validate_names(self, user_input: Dict[str, Any]) -> Dict[str, str]:
        """Validate all provided names (excludes IP address)."""
        errors = {}
        used_names = set()

        for key, value in user_input.items():
            # Skip IP address validation (handled separately)
            if key == "device_ip":
                continue
                
            name = str(value).strip()
            
            if not name:
                errors[key] = "name_required"
                continue
                
            if len(name) > MAX_NAME_LENGTH:
                errors[key] = "name_too_long"
                continue
                
            if not NAME_PATTERN.match(name):
                errors[key] = "invalid_characters"
                continue
                
            # Check for duplicates
            name_lower = name.lower()
            if name_lower in used_names:
                errors[key] = "name_duplicate"
                continue
                
            # ONLY add to used_names if ALL validations passed
            used_names.add(name_lower)

        return errors

    async def _update_entity_names_if_changed(self, new_data: Dict[str, Any]) -> None:
        """Update entity friendly names when port names change."""
        try:
            from homeassistant.helpers import entity_registry as er
            entity_registry = er.async_get(self.hass)

            old_data = self.config_entry.data
            device_unique_id = old_data["device_unique_id"]
            port_count = old_data.get("port_count", 6)

            # Check for port name changes
            port_name_changes = {}
            for port_id in range(1, port_count + 1):
                port_key = f"port_{port_id}_name"
                old_name = old_data.get(port_key, f"Port {port_id}")
                new_name = new_data.get(port_key, f"Port {port_id}")

                if old_name != new_name:
                    port_name_changes[port_id] = {"old": old_name, "new": new_name}

            # Check for device name changes
            device_name_changed = old_data.get("device_name") != new_data.get("device_name")

            if not port_name_changes and not device_name_changed:
                return  # No name changes to apply

            _LOGGER.debug("Updating entity names for %s: %d port name changes, device name changed: %s",
                        old_data["device_name"], len(port_name_changes), device_name_changed)

            # Update port entities (switches and sensors)
            for port_id, change in port_name_changes.items():
                await self._update_port_entity_names(entity_registry, device_unique_id, port_id, change["new"])

            # Update device name in all entities if device name changed
            if device_name_changed:
                await self._update_device_name_in_entities(entity_registry, device_unique_id, new_data["device_name"])

        except Exception as err:
            _LOGGER.error("Failed to update entity names: %s", err)

    async def _update_port_entity_names(self, entity_registry, device_unique_id: str, port_id: int, new_port_name: str) -> None:
        """Update entity names for a specific port."""
        # Update switch entity
        switch_unique_id = f"{device_unique_id}_{port_id}"
        switch_entity_id = entity_registry.async_get_entity_id("switch", "maxsmart", switch_unique_id)

        if switch_entity_id:
            entity_registry.async_update_entity(
                switch_entity_id,
                name=new_port_name
            )
            _LOGGER.debug("Updated switch entity name: %s -> %s", switch_entity_id, new_port_name)

        # Update power sensor entity
        sensor_unique_id = f"{device_unique_id}_{port_id}_power"
        sensor_entity_id = entity_registry.async_get_entity_id("sensor", "maxsmart", sensor_unique_id)

        if sensor_entity_id:
            entity_registry.async_update_entity(
                sensor_entity_id,
                name=f"{new_port_name} Power"
            )
            _LOGGER.debug("Updated sensor entity name: %s -> %s Power", sensor_entity_id, new_port_name)

    async def _update_device_name_in_entities(self, entity_registry, device_unique_id: str, new_device_name: str) -> None:
        """Update device name in master entities (for multi-port devices)."""
        # Note: new_device_name is intentionally not used here to keep entity names simple
        # Update master switch
        master_switch_unique_id = f"{device_unique_id}_0"
        master_switch_entity_id = entity_registry.async_get_entity_id("switch", "maxsmart", master_switch_unique_id)

        if master_switch_entity_id:
            entity_registry.async_update_entity(
                master_switch_entity_id,
                name="Master"  # Keep it simple, just "Master"
            )
            _LOGGER.debug("Updated master switch entity name: %s", master_switch_entity_id)

        # Update total power sensor
        total_power_unique_id = f"{device_unique_id}_0_power"
        total_power_entity_id = entity_registry.async_get_entity_id("sensor", "maxsmart", total_power_unique_id)

        if total_power_entity_id:
            entity_registry.async_update_entity(
                total_power_entity_id,
                name="Total Power"  # Keep it simple, just "Total Power"
            )
            _LOGGER.debug("Updated total power sensor entity name: %s", total_power_entity_id)

    async def async_step_confirm_ip_change(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Confirm IP change when new IP doesn't respond."""
        if user_input is None:
            # Show confirmation form
            new_ip = getattr(self, '_pending_new_ip', "Unknown")
            return self.async_show_form(
                step_id="confirm_ip_change",
                data_schema=vol.Schema({
                    vol.Required("confirm", default=False): bool,
                }),
                description_placeholders={
                    "device_name": self.config_entry.data.get("device_name", "Unknown"),
                    "new_ip": new_ip,
                }
            )

        if user_input.get("confirm", False):
            # User confirmed - proceed with IP change
            return await self._process_ip_change(getattr(self, '_pending_user_input', {}))
        else:
            # User cancelled - return to main form
            return await self.async_step_init()

    async def _test_ip_connection(self, ip_address: str) -> bool:
        """Test if IP address responds to MaxSmart connection."""
        try:
            from maxsmart import MaxSmartDevice

            _LOGGER.debug("Testing connection to IP %s", ip_address)
            test_device = MaxSmartDevice(ip_address)
            await test_device.initialize_device()
            await test_device.close()

            _LOGGER.debug("✅ IP TEST: %s responds correctly", ip_address)
            return True

        except Exception as err:
            _LOGGER.warning("❌ IP TEST: %s doesn't respond: %s", ip_address, err)
            return False

    async def _process_ip_change(self, user_input: Dict[str, Any]) -> FlowResult:
        """Process the IP change after validation/confirmation."""
        # Get old IP BEFORE updating entry
        old_ip = self.config_entry.data.get("device_ip")
        new_ip = user_input["device_ip"].strip()

        # Only proceed if IP actually changed
        if old_ip == new_ip:
            _LOGGER.debug("IP address unchanged for %s: %s",
                         self.config_entry.data["device_name"], old_ip)
            # No IP change - just update other data
            new_data = {**self.config_entry.data}
            new_data.update(user_input)

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data
            )

            # Update entity names if port names changed
            await self._update_entity_names_if_changed(new_data)

            # Reload the integration to apply changes
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)

            return self.async_create_entry(title="", data={})

        # Update config entry data
        new_data = {**self.config_entry.data}
        new_data.update(user_input)

        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data=new_data
        )

        _LOGGER.info("IP address changed for %s: %s → %s",
                   self.config_entry.data["device_name"], old_ip, new_ip)

        # Show notification about IP change
        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "MaxSmart IP Address Updated",
                    "message": f"Device '{self.config_entry.data['device_name']}' IP address updated to {new_ip}. "
                              f"The device will reconnect automatically.",
                    "notification_id": f"maxsmart_ip_change_{self.config_entry.entry_id}"
                }
            )
        except Exception as err:
            _LOGGER.warning("Failed to show IP change notification: %s", err)

        # Update entity names if port names changed
        await self._update_entity_names_if_changed(new_data)

        # Reload the integration to apply changes
        await self.hass.config_entries.async_reload(self.config_entry.entry_id)

        return self.async_create_entry(title="", data={})
