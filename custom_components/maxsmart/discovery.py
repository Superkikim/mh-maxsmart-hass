# custom_components/maxsmart/discovery.py
"""Minimal MaxSmart discovery - no background, no complexity."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from maxsmart import MaxSmartDiscovery
from maxsmart.exceptions import DiscoveryError

_LOGGER = logging.getLogger(__name__)

async def async_discover_devices() -> List[Dict[str, Any]]:
    """
    Simple device discovery wrapper.
    
    Returns:
        List of discovered devices or empty list
    """
    try:
        _LOGGER.debug("Starting MaxSmart device discovery")
        devices = await MaxSmartDiscovery.discover_maxsmart()
        
        if devices:
            _LOGGER.info("Found %d MaxSmart device(s)", len(devices))
            for device in devices:
                _LOGGER.debug("Device: %s (%s) - FW: %s", 
                            device.get("name", "Unknown"), 
                            device.get("ip", "Unknown"), 
                            device.get("ver", "Unknown"))
        else:
            _LOGGER.info("No MaxSmart devices found on network")
            
        return devices
        
    except DiscoveryError as err:
        _LOGGER.warning("MaxSmart discovery failed: %s", err)
        return []
        
    except Exception as err:
        _LOGGER.error("Unexpected error during MaxSmart discovery: %s", err)
        return []

async def async_discover_device_by_ip(ip_address: str) -> Dict[str, Any] | None:
    """
    Discover specific device by IP.
    
    Args:
        ip_address: IP address to check
        
    Returns:
        Device dict or None if not found
    """
    try:
        _LOGGER.debug("Discovering MaxSmart device at %s", ip_address)
        devices = await MaxSmartDiscovery.discover_maxsmart(ip=ip_address)
        
        if devices:
            device = devices[0]  # Should only be one for unicast
            _LOGGER.info("Found MaxSmart device: %s (%s) - FW: %s", 
                        device.get("name", "Unknown"), 
                        device.get("ip", "Unknown"), 
                        device.get("ver", "Unknown"))
            return device
        else:
            _LOGGER.warning("No MaxSmart device found at %s", ip_address)
            return None
            
    except DiscoveryError as err:
        _LOGGER.warning("Discovery failed for %s: %s", ip_address, err)
        return None
        
    except Exception as err:
        _LOGGER.error("Unexpected error discovering %s: %s", ip_address, err)
        return None