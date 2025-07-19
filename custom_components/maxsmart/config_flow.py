# custom_components/maxsmart/config_flow.py
"""Config flow for MaxSmart integration."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.data_entry_flow import FlowResult

from maxsmart import MaxSmartDiscovery, MaxSmartDevice
from maxsmart.exceptions import DiscoveryError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class MaxSmartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MaxSmart devices."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}

        if user_input is None:
            # Try automatic discovery first
            try:
                devices = await MaxSmartDiscovery.discover_maxsmart()
                if devices:
                    # For now, just take the first device
                    device = devices[0]
                    return await self._create_entry_from_device(device)
                else:
                    _LOGGER.info("No devices found automatically, showing manual form")
            except Exception as err:
                _LOGGER.warning("Discovery failed: %s", err)
                errors["base"] = "discovery_failed"

        else:
            # Manual IP provided
            ip_address = user_input[CONF_IP_ADDRESS].strip()
            
            try:
                devices = await MaxSmartDiscovery.discover_maxsmart(ip=ip_address)
                if devices:
                    device = devices[0]
                    return await self._create_entry_from_device(device)
                else:
                    errors["ip_address"] = "no_device_found"
            except Exception as err:
                _LOGGER.error("Manual discovery failed: %s", err)
                errors["ip_address"] = "connection_error"

        # Show form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_IP_ADDRESS): str,
            }),
            errors=errors,
        )

    async def _create_entry_from_device(self, device: Dict[str, Any]) -> FlowResult:
        """Create config entry from discovered device."""
        # Check if already configured
        await self.async_set_unique_id(device["sn"])
        self._abort_if_unique_id_configured()
        
        # Create entry data
        entry_data = {
            "device_unique_id": device["sn"],
            "device_ip": device["ip"],
            "device_name": device["name"],
            "sw_version": device["ver"],
        }
        
        return self.async_create_entry(
            title=f"MaxSmart {device['name']}",
            data=entry_data,
        )