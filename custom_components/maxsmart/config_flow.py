# custom_components/maxsmart/config_flow.py
"""Config flow for MaxSmart integration - creates discovery cards for all devices."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from maxsmart import MaxSmartDiscovery, MaxSmartDevice
from maxsmart.exceptions import (
    DiscoveryError,
    ConnectionError as MaxSmartConnectionError,
    DeviceTimeoutError,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Validation patterns - Support for accented characters
VALID_NAME_PATTERN = re.compile(r'^[\w\s\-\.àáâäèéêëìíîïòóôöùúûüÿçñÀÁÂÄÈÉÊËÌÍÎÏÒÓÔÖÙÚÛÜŸÇÑ]+$')
MAX_NAME_LENGTH = 50

class MaxSmartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MaxSmart devices."""

    VERSION = 2
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_device: Optional[Dict[str, Any]] = None

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step - discovery or manual IP."""
        errors: Dict[str, str] = {}

        if user_input is None:
            # First try automatic discovery
            _LOGGER.info("Starting automatic MaxSmart device discovery")
            try:
                discovered_devices = await self._async_discover_devices()
                if discovered_devices:
                    _LOGGER.info("Found %d MaxSmart devices", len(discovered_devices))
                    
                    # Create discovery flows for all devices except one
                    await self._async_create_discovery_flows(discovered_devices[1:])
                    
                    # Configure the first device in this flow
                    self._discovered_device = discovered_devices[0]
                    return await self.async_step_customize_names()
                else:
                    _LOGGER.info("No devices found automatically, showing manual input form")
                    
            except Exception as err:
                _LOGGER.warning("Automatic discovery failed: %s", err)
                errors["base"] = "discovery_failed"

        else:
            # Manual IP provided
            ip_address = user_input[CONF_IP_ADDRESS].strip()
            if not self._is_valid_ip(ip_address):
                errors["ip_address"] = "invalid_ip"
            else:
                try:
                    discovered_devices = await self._async_discover_devices(ip_address)
                    if discovered_devices:
                        # Single device found, configure it in this flow
                        self._discovered_device = discovered_devices[0]
                        return await self.async_step_customize_names()
                    else:
                        errors["ip_address"] = "no_device_found"
                        
                except Exception as err:
                    _LOGGER.error("Manual discovery failed for %s: %s", ip_address, err)
                    errors["ip_address"] = "connection_error"

        # Show manual input form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_IP_ADDRESS): str,
            }),
            errors=errors,
            description_placeholders={
                "discovery_info": "Enter IP manually if automatic discovery failed"
            }
        )

    async def async_step_discovery(
        self, discovery_info: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle discovery step for individual device flows."""
        if discovery_info and "device_data" in discovery_info:
            device = discovery_info["device_data"]
            device_title = discovery_info.get("device_title", device["name"])
            
            # Check if already configured
            if self._is_device_configured(device["sn"]):
                return self.async_abort(reason="device_already_configured")
                
            # Set unique_id for this flow
            await self.async_set_unique_id(device["sn"])
            self._abort_if_unique_id_configured()
            
            # Store device and go to customization
            self._discovered_device = device
            return await self.async_step_customize_names()
        
        return self.async_abort(reason="no_device")

    async def _async_create_discovery_flows(self, devices: List[Dict[str, Any]]) -> None:
        """Create discovery flows for all devices except the current one."""
        for device in devices:
            # Skip if already configured
            if self._is_device_configured(device["sn"]):
                _LOGGER.info("Device %s already configured, skipping discovery flow", device["sn"])
                continue
                
            # Generate smart title for the device
            device_title = await self._async_generate_device_title(device)
            
            try:
                # Create discovery flow for this device
                _LOGGER.info("Creating discovery flow for device: %s", device_title)
                
                await self.hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": "discovery"},
                    data={
                        "device_data": device,
                        "device_title": device_title
                    }
                )
                
            except Exception as err:
                _LOGGER.error("Failed to create discovery flow for device %s: %s", device["sn"], err)

    async def async_step_customize_names(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle device and port name customization."""
        if not self._discovered_device:
            return self.async_abort(reason="no_device")

        device = self._discovered_device
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Validate user input
            validation_errors = self._validate_names(user_input, device)
            if not validation_errors:
                # Create the config entry for THIS device
                entry_data = await self._async_create_entry_data(device, user_input)
                title = user_input.get("device_name", device["name"])
                
                # Create entry for current device - this ends the flow
                return self.async_create_entry(
                    title=f"MaxSmart {title}",
                    data=entry_data,
                )
                
            else:
                errors.update(validation_errors)

        # Get device info and default names
        try:
            device_info = await self._async_get_device_info(device)
            schema = self._build_customize_schema(device_info)
            
            description = (
                f"Device: {device['name']} ({device['ip']})\n"
                f"Firmware: {device['ver']}\n"
                f"Ports: {len(device_info['port_names'])}"
            )
            
            return self.async_show_form(
                step_id="customize_names",
                data_schema=schema,
                errors=errors,
                description_placeholders={
                    "device_info": description
                }
            )
            
        except Exception as err:
            _LOGGER.error("Error getting device info for %s: %s", device["ip"], err)
            return self.async_abort(reason="device_info_error")

    async def _async_discover_devices(
        self, target_ip: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Discover MaxSmart devices with error handling."""
        try:
            if target_ip:
                devices = await MaxSmartDiscovery.discover_maxsmart(ip=target_ip)
            else:
                devices = await MaxSmartDiscovery.discover_maxsmart()
                
            # Filter out already configured devices
            filtered_devices = []
            for device in devices or []:
                if not self._is_device_configured(device["sn"]):
                    filtered_devices.append(device)
                else:
                    _LOGGER.info("Device %s already configured, skipping", device["sn"])
                    
            return filtered_devices
            
        except DiscoveryError as err:
            _LOGGER.error("Discovery error: %s", err)
            raise
        except Exception as err:
            _LOGGER.error("Unexpected discovery error: %s", err)
            raise

    async def _async_generate_device_title(self, device: Dict[str, Any]) -> str:
        """Generate a smart title for the device based on available info."""
        device_ip = device["ip"]
        device_sn = device["sn"]
        
        try:
            # Try to get device custom name
            device_obj = MaxSmartDevice(device_ip)
            await device_obj.initialize_device()
            
            try:
                port_names_dict = await device_obj.retrieve_port_names()
                if port_names_dict and "Port 0" in port_names_dict:
                    # Device name available: "Salon (172.30.47.76, ABC123)"
                    device_name = port_names_dict["Port 0"]
                    return f"{device_name} ({device_ip}, {device_sn})"
                else:
                    raise ValueError("No custom name available")
                    
            except Exception:
                # No custom name: "172.30.47.76 (ABC123)"
                return f"{device_ip} ({device_sn})"
                
        except Exception as err:
            _LOGGER.warning("Could not get device info for title: %s", err)
            # Fallback: "172.30.47.76 (ABC123)"
            return f"{device_ip} ({device_sn})"
            
        finally:
            if 'device_obj' in locals():
                await device_obj.close()

    async def _async_get_device_info(self, device: Dict[str, Any]) -> Dict[str, Any]:
        """Get device information including port names."""
        device_obj = MaxSmartDevice(device["ip"])
        
        try:
            await device_obj.initialize_device()
            
            # Try to get port names from device
            try:
                port_names_dict = await device_obj.retrieve_port_names()
                if port_names_dict:
                    device_name = port_names_dict.get("Port 0", device["name"])
                    # Extract port names (Port 1, Port 2, etc.)
                    port_names = []
                    port_num = 1
                    while f"Port {port_num}" in port_names_dict:
                        port_names.append(port_names_dict[f"Port {port_num}"])
                        port_num += 1
                else:
                    raise ValueError("No port names available")
                    
            except Exception:
                # Fallback to defaults - utilise IP comme nom de device si pas de noms
                num_ports = len(device.get("pname", [])) or 1
                device_name = device["ip"]  # IP comme nom par défaut
                port_names = [f"Port {i}" for i in range(1, num_ports + 1)]
                
            return {
                "device_name": device_name,
                "port_names": port_names,
                "num_ports": len(port_names)
            }
            
        finally:
            await device_obj.close()

    def _build_customize_schema(self, device_info: Dict[str, Any]) -> vol.Schema:
        """Build the schema for name customization."""
        schema_dict = {
            vol.Required("device_name", default=device_info["device_name"]): str,
        }
        
        # Add port name fields
        for i, port_name in enumerate(device_info["port_names"], 1):
            schema_dict[vol.Required(f"port_{i}_name", default=port_name)] = str
            
        return vol.Schema(schema_dict)

    def _validate_names(
        self, user_input: Dict[str, Any], device: Dict[str, Any]
    ) -> Dict[str, str]:
        """Validate user-provided names."""
        errors = {}
        names_used = []

        # Validate device name
        device_name = user_input.get("device_name", "").strip()
        if not device_name:
            errors["device_name"] = "name_required"
        elif len(device_name) > MAX_NAME_LENGTH:
            errors["device_name"] = "name_too_long"
        elif not VALID_NAME_PATTERN.match(device_name):
            errors["device_name"] = "invalid_characters"
        else:
            names_used.append(device_name.lower())

        # Validate port names
        port_keys = [key for key in user_input.keys() if key.startswith("port_") and key.endswith("_name")]
        for port_key in port_keys:
            port_name = user_input.get(port_key, "").strip()
            if not port_name:
                errors[port_key] = "name_required"
            elif len(port_name) > MAX_NAME_LENGTH:
                errors[port_key] = "name_too_long"
            elif not VALID_NAME_PATTERN.match(port_name):
                errors[port_key] = "invalid_characters"
            elif port_name.lower() in names_used:
                errors[port_key] = "name_duplicate"
            else:
                names_used.append(port_name.lower())

        return errors

    async def _async_create_entry_data(
        self, device: Dict[str, Any], user_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create the entry data structure."""
        device_name = user_input["device_name"].strip()
        
        # Extract port names from user input
        port_names = []
        port_keys = sorted([key for key in user_input.keys() if key.startswith("port_") and key.endswith("_name")])
        for port_key in port_keys:
            port_names.append(user_input[port_key].strip())

        # Build port structure
        port_data = {
            "master": {"port_id": 0, "port_name": "Master"},
            "individual_ports": [
                {"port_id": i + 1, "port_name": f"{i + 1}. {name}"}
                for i, name in enumerate(port_names)
            ],
        }

        return {
            "device_unique_id": device["sn"],
            "device_ip": device["ip"],
            "device_name": device_name,
            "sw_version": device["ver"],
            "ports": port_data,
            "custom_names": {
                "device": device_name,
                "ports": port_names
            }
        }

    def _is_device_configured(self, serial_number: str) -> bool:
        """Check if device is already configured."""
        for entry in self._async_current_entries():
            if entry.data.get("device_unique_id") == serial_number:
                return True
        return False

    def _is_valid_ip(self, ip: str) -> bool:
        """Validate IP address format."""
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        try:
            return all(0 <= int(part) <= 255 for part in parts)
        except ValueError:
            return False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> MaxSmartOptionsFlow:
        """Get the options flow."""
        return MaxSmartOptionsFlow(config_entry)

class MaxSmartOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for MaxSmart devices."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Validate and update names
            errors = self._validate_options(user_input)
            if not errors:
                return self.async_create_entry(title="", data=user_input)
        else:
            user_input = self._get_current_options()

        return self.async_show_form(
            step_id="init",
            data_schema=self._build_options_schema(user_input),
            errors=errors if 'errors' in locals() else {}
        )

    def _get_current_options(self) -> Dict[str, Any]:
        """Get current options/names."""
        custom_names = self.config_entry.data.get("custom_names", {})
        options = {
            "device_name": custom_names.get("device", self.config_entry.data.get("device_name", "")),
        }
        
        port_names = custom_names.get("ports", [])
        for i, name in enumerate(port_names, 1):
            options[f"port_{i}_name"] = name
            
        return options

    def _build_options_schema(self, current_options: Dict[str, Any]) -> vol.Schema:
        """Build options schema."""
        schema_dict = {
            vol.Required("device_name", default=current_options.get("device_name", "")): str,
        }
        
        # Add port fields based on current config
        ports = self.config_entry.data.get("ports", {}).get("individual_ports", [])
        for i, port in enumerate(ports, 1):
            current_name = current_options.get(f"port_{i}_name", f"Port {i}")
            schema_dict[vol.Required(f"port_{i}_name", default=current_name)] = str
            
        return vol.Schema(schema_dict)

    def _validate_options(self, options: Dict[str, Any]) -> Dict[str, str]:
        """Validate options input."""
        errors = {}
        names_used = []

        # Same validation as config flow
        device_name = options.get("device_name", "").strip()
        if not device_name:
            errors["device_name"] = "name_required"
        elif len(device_name) > MAX_NAME_LENGTH:
            errors["device_name"] = "name_too_long"
        elif not VALID_NAME_PATTERN.match(device_name):
            errors["device_name"] = "invalid_characters"
        else:
            names_used.append(device_name.lower())

        # Validate port names
        port_keys = [key for key in options.keys() if key.startswith("port_") and key.endswith("_name")]
        for port_key in port_keys:
            port_name = options.get(port_key, "").strip()
            if not port_name:
                errors[port_key] = "name_required"
            elif len(port_name) > MAX_NAME_LENGTH:
                errors[port_key] = "name_too_long"
            elif not VALID_NAME_PATTERN.match(port_name):
                errors[port_key] = "invalid_characters"
            elif port_name.lower() in names_used:
                errors[port_key] = "name_duplicate"
            else:
                names_used.append(port_name.lower())

        return errors