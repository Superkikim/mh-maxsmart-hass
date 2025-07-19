# custom_components/maxsmart/config_flow.py
"""Config flow for MaxSmart integration with discovery cards and manual addition."""

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
NAME_PATTERN = re.compile(r'^[a-zA-Z0-9\s\-_\.]+$')
MAX_NAME_LENGTH = 50

class MaxSmartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for MaxSmart devices."""

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
        """Handle the initial step - discovery + manual option."""
        errors: Dict[str, str] = {}

        if user_input is None:
            # Auto-discovery on first load
            try:
                _LOGGER.debug("Starting automatic device discovery")
                devices = await async_discover_devices()
                
                if devices:
                    # Create discovery flows for each device found
                    discovery_count = 0
                    for device in devices:
                        if not self._is_device_configured(device["sn"]):
                            # Create discovery flow for this device
                            self.hass.async_create_task(
                                self.hass.config_entries.flow.async_init(
                                    DOMAIN,
                                    context={"source": "discovery"},
                                    data=device
                                )
                            )
                            discovery_count += 1
                    
                    if discovery_count > 0:
                        # Discovery cards created - abort this flow
                        return self.async_abort(
                            reason="devices_found",
                            description_placeholders={"count": str(discovery_count)}
                        )
                    else:
                        # All devices already configured
                        return self.async_abort(reason="devices_configured")
                        
                # No devices found - show manual form with discovery info
                _LOGGER.info("No devices found automatically, showing manual form")
                
            except Exception as err:
                _LOGGER.warning("Discovery failed: %s", err)
                errors["base"] = "discovery_failed"

        else:
            # Handle manual IP input or "add manually" button
            if user_input.get("add_manually"):
                # User clicked "Add manually" - continue to IP form
                pass
            else:
                # Manual IP provided
                ip_address = user_input[CONF_IP_ADDRESS].strip()
                
                # Validate IP format
                try:
                    ipaddress.ip_address(ip_address)
                except ValueError:
                    errors["ip_address"] = "invalid_ip"
                else:
                    # Try to discover at specific IP
                    try:
                        device = await async_discover_device_by_ip(ip_address)
                        if device:
                            # Check if already configured
                            if self._is_device_configured(device["sn"]):
                                return self.async_abort(reason="device_already_configured")
                            
                            self._discovered_device = device
                            return await self.async_step_customize_names()
                        else:
                            errors["ip_address"] = "no_device_found"
                    except Exception as err:
                        _LOGGER.error("Manual discovery failed: %s", err)
                        errors["ip_address"] = "connection_error"

        # Show manual IP form with discovery status
        discovery_status = "No devices found automatically" if not errors else "Discovery failed"
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_IP_ADDRESS): str,
                vol.Optional("add_manually", default=False): bool,
            }),
            errors=errors,
            description_placeholders={
                "discovery_status": discovery_status
            }
        )

    async def async_step_discovery(self, discovery_info: Dict[str, Any]) -> FlowResult:
        """Handle discovery from automatic discovery or background discovery."""
        device_sn = discovery_info.get("sn")
        device_name = discovery_info.get("name", "Unknown Device")
        device_ip = discovery_info.get("ip", "Unknown")
        
        if not device_sn:
            return self.async_abort(reason="no_device")
            
        # Check if already configured
        if self._is_device_configured(device_sn):
            return self.async_abort(reason="device_already_configured")
            
        # Set unique ID to prevent duplicates
        await self.async_set_unique_id(device_sn)
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
        """Handle device and port name customization."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Validate all names
            validation_errors = self._validate_names(user_input)
            if validation_errors:
                errors.update(validation_errors)
            else:
                # Create the config entry
                return await self._create_entry_from_names(user_input)

        # Determine port count and default names
        device = self._discovered_device
        port_count = self._get_port_count(device["sn"])
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

        # Device info for display
        device_info = (
            f"Device: {device.get('name', 'Unknown')}\n"
            f"IP: {device['ip']}\n"
            f"Serial: {device['sn']}\n" 
            f"Firmware: {device.get('ver', 'Unknown')}\n"
            f"Ports: {port_count}"
        )

        return self.async_show_form(
            step_id="customize_names",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "device_info": device_info
            }
        )

    async def _create_entry_from_names(self, names: Dict[str, Any]) -> FlowResult:
        """Create config entry with device and name data."""
        device = self._discovered_device
        
        # Set unique ID to prevent duplicates
        await self.async_set_unique_id(device["sn"])
        self._abort_if_unique_id_configured()
        
        # Build entry data
        entry_data = {
            "device_unique_id": device["sn"],
            "device_ip": device["ip"],
            "device_name": names["device_name"],
            "sw_version": device.get("ver", "Unknown"),
        }
        
        # Add port names
        port_count = self._get_port_count(device["sn"])
        for port_id in range(1, port_count + 1):
            port_key = f"port_{port_id}_name"
            entry_data[port_key] = names[port_key]
        
        return self.async_create_entry(
            title=f"MaxSmart {names['device_name']}",
            data=entry_data,
        )

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

    def _get_port_count(self, serial_number: str) -> int:
        """Determine port count from serial number."""
        try:
            if len(serial_number) >= 4:
                port_char = serial_number[3]
                if port_char == '1':
                    return 1
                elif port_char == '6':
                    return 6
            return 6  # Default
        except Exception:
            return 6

    def _is_device_configured(self, serial_number: str) -> bool:
        """Check if device is already configured."""
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.data.get("device_unique_id") == serial_number:
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
        port_count = self._get_port_count(current_data["device_unique_id"])

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

    def _get_port_count(self, serial_number: str) -> int:
        """Determine port count from serial number."""
        try:
            if len(serial_number) >= 4:
                port_char = serial_number[3]
                if port_char == '1':
                    return 1
                elif port_char == '6':
                    return 6
            return 6
        except Exception:
            return 6