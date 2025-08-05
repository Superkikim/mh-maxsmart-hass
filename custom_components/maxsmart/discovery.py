# custom_components/maxsmart/discovery.py
"""Enhanced MaxSmart discovery with hardware identification integration."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from maxsmart import MaxSmartDiscovery, MaxSmartDevice
from maxsmart.exceptions import DiscoveryError, ConnectionError as MaxSmartConnectionError

_LOGGER = logging.getLogger(__name__)

async def async_discover_devices(enhance_with_hardware: bool = True) -> List[Dict[str, Any]]:
    """
    Enhanced device discovery with optional hardware identification.
    
    Args:
        enhance_with_hardware: Whether to fetch hardware IDs (CPU, MAC, etc.)
        
    Returns:
        List of discovered devices with enhanced identification data
    """
    try:
        _LOGGER.debug("Starting MaxSmart device discovery (enhanced=%s)", enhance_with_hardware)
        
        # Use maxsmart module's enhanced discovery if available
        if hasattr(MaxSmartDiscovery, 'discover_maxsmart') and enhance_with_hardware:
            devices = await MaxSmartDiscovery.discover_maxsmart(
                enhance_with_hardware_ids=True
            )
        else:
            # Fallback to basic discovery
            devices = await MaxSmartDiscovery.discover_maxsmart()
            
            # Manual enhancement if needed
            if enhance_with_hardware and devices:
                devices = await _enhance_devices_manually(devices)
        
        if devices:
            _LOGGER.info("🔍 DISCOVERY: Found %d MaxSmart device(s)", len(devices))
            for i, device in enumerate(devices):
                _LOGGER.debug("🔍 DISCOVERY: Device %d = %s", i+1, device)
                _LOGGER.debug("🔍 DISCOVERY: Device %d - IP: %s, MAC: %s, CPU: %s",
                             i+1, device.get("ip"), device.get("mac"), device.get("cpuid"))
        else:
            _LOGGER.info("🔍 DISCOVERY: No MaxSmart devices found on network")

        # Return devices exactly as provided by maxsmart library - NO NORMALIZATION!
        return devices or []
        
    except DiscoveryError as err:
        _LOGGER.warning("MaxSmart discovery failed: %s", err)
        return []
        
    except Exception as err:
        _LOGGER.error("Unexpected error during MaxSmart discovery: %s", err)
        return []

async def async_discover_device_by_ip(ip_address: str, enhance_with_hardware: bool = True) -> Dict[str, Any] | None:
    """
    Enhanced discovery of specific device by IP with hardware identification.
    
    Args:
        ip_address: IP address to check
        enhance_with_hardware: Whether to fetch hardware IDs
        
    Returns:
        Enhanced device dict or None if not found
    """
    try:
        _LOGGER.debug("Discovering MaxSmart device at %s (enhanced=%s)", ip_address, enhance_with_hardware)
        
        # Use maxsmart module's enhanced discovery if available
        if hasattr(MaxSmartDiscovery, 'discover_maxsmart') and enhance_with_hardware:
            devices = await MaxSmartDiscovery.discover_maxsmart(
                ip=ip_address,
                enhance_with_hardware_ids=True
            )
        else:
            # Fallback to basic discovery
            devices = await MaxSmartDiscovery.discover_maxsmart(ip=ip_address)
            
            # Manual enhancement if needed
            if enhance_with_hardware and devices:
                devices = await _enhance_devices_manually(devices)
        
        if devices:
            device = devices[0]  # Should only be one for unicast
            _LOGGER.info("Found MaxSmart device: %s (%s) - Enhanced ID: %s", 
                        device.get("name", "Unknown"), 
                        device.get("ip", "Unknown"),
                        _get_device_summary_id(device))
            # Return device exactly as provided by maxsmart library - NO NORMALIZATION!
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

async def _enhance_devices_manually(devices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Manually enhance devices with hardware identification when module doesn't support it.
    
    Args:
        devices: List of basic devices from discovery
        
    Returns:
        List of enhanced devices with hardware IDs
    """
    enhanced_devices = []
    
    for device in devices:
        enhanced_device = device.copy()
        ip = device["ip"]
        
        try:
            # Create temporary device instance
            temp_device = MaxSmartDevice(ip)
            await temp_device.initialize_device()
            
            # Get hardware identifiers
            try:
                hw_ids = await temp_device.get_device_identifiers()
                enhanced_device["hw_ids"] = hw_ids
                enhanced_device["cpu_id"] = hw_ids.get("cpuid", "")
                enhanced_device["pclmac"] = hw_ids.get("pclmac", "")
                
                # Try to get MAC via ARP as fallback
                try:
                    mac_arp = await temp_device.get_mac_address_via_arp()
                    enhanced_device["mac_address"] = mac_arp or hw_ids.get("pclmac", "")
                except:
                    enhanced_device["mac_address"] = hw_ids.get("pclmac", "")
                
                # Determine identification method
                if hw_ids.get("cpuid"):
                    enhanced_device["identification_method"] = "cpu_id"
                elif enhanced_device.get("mac_address"):
                    enhanced_device["identification_method"] = "mac_address"
                elif device.get("sn"):
                    enhanced_device["identification_method"] = "udp_serial"
                else:
                    enhanced_device["identification_method"] = "ip_fallback"
                
                _LOGGER.debug("Enhanced device %s: method=%s", ip, enhanced_device["identification_method"])
                
            except Exception as e:
                # Hardware ID fetch failed
                _LOGGER.debug("Failed to get hardware IDs for %s: %s", ip, e)
                enhanced_device["hw_ids"] = {}
                enhanced_device["cpu_id"] = ""
                enhanced_device["mac_address"] = ""
                enhanced_device["identification_method"] = "ip_fallback"
                
        except Exception as e:
            # Device initialization failed
            _LOGGER.debug("Failed to initialize device %s for enhancement: %s", ip, e)
            enhanced_device["hw_ids"] = {}
            enhanced_device["cpu_id"] = ""
            enhanced_device["mac_address"] = ""
            enhanced_device["identification_method"] = "ip_fallback"
            
        finally:
            # Cleanup
            try:
                if 'temp_device' in locals():
                    await temp_device.close()
            except:
                pass
                
        enhanced_devices.append(enhanced_device)
        
    return enhanced_devices

def _normalize_device_data(devices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize device data to ensure consistent structure.
    
    Args:
        devices: Raw devices from discovery
        
    Returns:
        Normalized devices with consistent fields
    """
    normalized_devices = []
    
    for device in devices:
        normalized = {
            # Core fields (always present)
            "ip": device.get("ip", ""),
            "name": device.get("name", ""),
            "sn": device.get("sn", ""),
            "ver": device.get("ver", ""),
            "pname": device.get("pname", []),
            
            # Enhanced identification fields
            "cpu_id": device.get("cpuid") or device.get("cpu_id", ""),
            "mac_address": device.get("mac_address", ""),
            "pclmac": device.get("pclmac", ""),
            "hw_ids": device.get("hw_ids", {}),
            "identification_method": device.get("identification_method", "udp_serial"),
            
            # Additional metadata
            "unique_id": device.get("unique_id", ""),
            "primary_id": device.get("primary_id", ""),
            "sn_reliable": device.get("sn_reliable", True),
        }
        
        normalized_devices.append(normalized)
    
    return normalized_devices

def _get_device_summary_id(device: Dict[str, Any]) -> str:
    """Get a summary ID for logging purposes."""
    if device.get("cpu_id"):
        return f"CPU:{device['cpu_id'][:12]}..."
    elif device.get("mac_address"):
        return f"MAC:{device['mac_address']}"
    elif device.get("sn"):
        return f"SN:{device['sn']}"
    else:
        return f"IP:{device.get('ip', 'unknown')}"

def _log_device_summary(device: Dict[str, Any]) -> None:
    """Log a summary of discovered device."""
    summary_id = _get_device_summary_id(device)
    method = device.get("identification_method", "unknown")
    
    _LOGGER.debug(
        "Device: %s (%s) - FW: %s, ID: %s [%s]",
        device.get("name", "Unknown"),
        device.get("ip", "Unknown"),
        device.get("ver", "Unknown"),
        summary_id,
        method.upper()
    )