# custom_components/maxsmart/discovery.py
"""Simple MaxSmart discovery wrapper - uses maxsmart library directly."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from maxsmart import MaxSmartDiscovery
from maxsmart.exceptions import DiscoveryError

_LOGGER = logging.getLogger(__name__)

async def async_discover_devices(enhance_with_hardware: bool = True) -> List[Dict[str, Any]]:
    """
    Simple device discovery using maxsmart library directly.
    
    Args:
        enhance_with_hardware: Whether to fetch hardware IDs (CPU, MAC, etc.)
        
    Returns:
        List of discovered devices exactly as returned by maxsmart library
    """
    try:
        _LOGGER.debug("🔍 DISCOVERY: Starting MaxSmart device discovery (enhanced=%s)", enhance_with_hardware)
        
        # Use maxsmart library directly - no custom logic!
        if enhance_with_hardware:
            devices = await MaxSmartDiscovery.discover_maxsmart(enhance_with_hardware_ids=True)
        else:
            devices = await MaxSmartDiscovery.discover_maxsmart()
        
        if devices:
            _LOGGER.debug("🔍 DISCOVERY: Found %d MaxSmart device(s)", len(devices))
            for i, device in enumerate(devices):
                _LOGGER.debug("🔍 DISCOVERY: Device %d = %s", i+1, device)
                _LOGGER.debug("🔍 DISCOVERY: Device %d - IP: %s, MAC: %s, CPU: %s", 
                             i+1, device.get("ip"), device.get("mac"), device.get("cpuid"))
        else:
            _LOGGER.debug("🔍 DISCOVERY: No MaxSmart devices found on network")
            
        # Return devices exactly as provided by maxsmart library
        return devices or []
        
    except DiscoveryError as err:
        _LOGGER.warning("🔍 DISCOVERY: MaxSmart discovery failed: %s", err)
        return []
        
    except Exception as err:
        _LOGGER.error("🔍 DISCOVERY: Unexpected error during MaxSmart discovery: %s", err)
        return []

async def async_discover_device_by_ip(ip_address: str, enhance_with_hardware: bool = True) -> Dict[str, Any] | None:
    """
    Simple device discovery by IP using maxsmart library directly.
    
    Args:
        ip_address: IP address to check
        enhance_with_hardware: Whether to fetch hardware IDs
        
    Returns:
        Device dict exactly as returned by maxsmart library or None if not found
    """
    try:
        _LOGGER.debug("🔍 DISCOVERY: Discovering MaxSmart device at %s (enhanced=%s)", ip_address, enhance_with_hardware)
        
        # Use maxsmart library directly - no custom logic!
        if enhance_with_hardware:
            devices = await MaxSmartDiscovery.discover_maxsmart(ip=ip_address, enhance_with_hardware_ids=True)
        else:
            devices = await MaxSmartDiscovery.discover_maxsmart(ip=ip_address)
        
        if devices:
            device = devices[0]  # Should only be one for unicast
            _LOGGER.debug("🔍 DISCOVERY: Found MaxSmart device: %s (%s)", 
                        device.get("name", "Unknown"), device.get("ip", "Unknown"))
            _LOGGER.debug("🔍 DISCOVERY: Device data = %s", device)
            return device
        else:
            _LOGGER.debug("🔍 DISCOVERY: No MaxSmart device found at %s", ip_address)
            return None
            
    except DiscoveryError as err:
        _LOGGER.warning("🔍 DISCOVERY: Discovery failed for %s: %s", ip_address, err)
        return None
        
    except Exception as err:
        _LOGGER.error("🔍 DISCOVERY: Unexpected error discovering %s: %s", ip_address, err)
        return None

# Simple wrapper that uses maxsmart library directly
