# custom_components/maxsmart/discovery.py
"""MaxSmart background discovery using async_track_time_interval."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, List

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers import discovery_flow

from maxsmart import MaxSmartDiscovery
from maxsmart.exceptions import DiscoveryError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DISCOVERY_INTERVAL = timedelta(minutes=10)  # Scan every 10 minutes

class MaxSmartBackgroundDiscovery:
    """Handle background discovery of MaxSmart devices."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the discovery component."""
        self.hass = hass
        self._discovered_devices: Dict[str, Dict[str, Any]] = {}
        self._discovery_active = False
        self._unsub_discovery = None

    async def async_start_discovery(self) -> None:
        """Start periodic discovery."""
        if self._discovery_active:
            return
            
        _LOGGER.info("Starting MaxSmart background discovery")
        self._discovery_active = True
        
        # Do initial discovery after a short delay (let HA finish startup)
        self.hass.async_create_task(self._async_initial_discovery())
        
        # Schedule periodic discovery
        self._unsub_discovery = async_track_time_interval(
            self.hass,
            self._async_discover_devices,
            DISCOVERY_INTERVAL
        )

    async def async_stop_discovery(self) -> None:
        """Stop periodic discovery."""
        if not self._discovery_active:
            return
            
        _LOGGER.info("Stopping MaxSmart background discovery")
        self._discovery_active = False
        
        if self._unsub_discovery:
            self._unsub_discovery()
            self._unsub_discovery = None

    async def _async_initial_discovery(self) -> None:
        """Run initial discovery after startup delay."""
        # Wait a bit for HA to finish startup
        await asyncio.sleep(30)  # 30 seconds delay
        await self._async_discover_devices()

    async def _async_discover_devices(self, now=None) -> None:
        """Discover MaxSmart devices and trigger flows for new ones."""
        try:
            _LOGGER.debug("Running MaxSmart background discovery scan")
            
            # Discover devices
            devices = await MaxSmartDiscovery.discover_maxsmart()
            
            if not devices:
                _LOGGER.debug("No MaxSmart devices found during background scan")
                return
                
            _LOGGER.debug("Background discovery found %d MaxSmart devices", len(devices))
            
            # Process each discovered device
            for device in devices:
                await self._async_process_discovered_device(device)
                
        except DiscoveryError as err:
            _LOGGER.warning("MaxSmart background discovery scan failed: %s", err)
        except Exception as err:
            _LOGGER.error("Unexpected error during MaxSmart background discovery: %s", err)

    async def _async_process_discovered_device(self, device: Dict[str, Any]) -> None:
        """Process a single discovered device."""
        device_sn = device["sn"]
        device_ip = device["ip"]
        
        # Check if we've seen this device before
        if device_sn in self._discovered_devices:
            # Update IP if changed
            if self._discovered_devices[device_sn]["ip"] != device_ip:
                _LOGGER.info("Device %s IP changed: %s -> %s", 
                           device_sn, self._discovered_devices[device_sn]["ip"], device_ip)
                self._discovered_devices[device_sn] = device
            return
            
        # Check if device is already configured
        if self._is_device_configured(device_sn):
            _LOGGER.debug("Device %s already configured, skipping", device_sn)
            self._discovered_devices[device_sn] = device
            return
            
        # New device found - trigger discovery notification
        _LOGGER.info("New MaxSmart device discovered: %s (%s)", device["name"], device_ip)
        
        try:
            # Create discovery flow using HA's discovery system
            result = await self.hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "discovery"},
                data=device
            )
            
            # Remember this device
            self._discovered_devices[device_sn] = device
            
            _LOGGER.info("Discovery flow created for device: %s (%s)", device["name"], device_ip)
            
        except Exception as err:
            _LOGGER.error("Failed to create discovery flow for device %s: %s", device_sn, err)

    def _is_device_configured(self, serial_number: str) -> bool:
        """Check if device is already configured."""
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.data.get("device_unique_id") == serial_number:
                return True
        return False

    @property
    def is_active(self) -> bool:
        """Return if discovery is active."""
        return self._discovery_active

async def async_setup_background_discovery(hass: HomeAssistant) -> None:
    """Set up MaxSmart background discovery."""
    _LOGGER.info("Setting up MaxSmart background discovery")
    
    # Create discovery instance
    discovery = MaxSmartBackgroundDiscovery(hass)
    
    # Store in hass data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["background_discovery"] = discovery
    
    # Start discovery
    await discovery.async_start_discovery()

async def async_stop_background_discovery(hass: HomeAssistant) -> None:
    """Stop MaxSmart background discovery."""
    if DOMAIN in hass.data and "background_discovery" in hass.data[DOMAIN]:
        _LOGGER.info("Stopping MaxSmart background discovery")
        discovery = hass.data[DOMAIN]["background_discovery"]
        await discovery.async_stop_discovery()
        hass.data[DOMAIN].pop("background_discovery")