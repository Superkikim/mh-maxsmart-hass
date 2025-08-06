"""
Messages and logging utilities for MaxSmart integration.
Centralizes all user-facing messages and logging patterns.
"""

from typing import Dict, Any
import logging

_LOGGER = logging.getLogger(__name__)

# Log message templates
LOG_MESSAGES = {
    # Setup and initialization
    "setup_start": "Setting up MaxSmart device: {device_name} at {ip}",
    "setup_success": "✅ SETUP: {device_name} - Successfully connected and initialized",
    "setup_failed": "❌ SETUP: {device_name} - Failed to initialize: {error}",
    
    # IP Recovery
    "ip_recovery_start": "🔍 IP RECOVERY: {device_name} - Starting recovery (Current: {old_ip}, MAC: {mac})",
    "ip_recovery_success": "✅ IP RECOVERY: {device_name} - Successfully changed {old_ip} → {new_ip}",
    "ip_recovery_failed": "❌ IP RECOVERY: {device_name} - Failed to find new IP",
    "ip_recovery_exhausted": "⚠️ IP RECOVERY: {device_name} - Exhausted {attempts}/{max_attempts} attempts",
    
    # ARP checks
    "arp_check_start": "🔍 ARP CHECK: {device_name} - Checking for IP change",
    "arp_ip_changed": "🚀 ARP CHECK: {device_name} - IP changed {old_ip} → {new_ip}",
    "arp_no_change": "🔍 ARP CHECK: {device_name} - No IP change detected",
    "arp_test_success": "✅ ARP CHECK: {device_name} - New IP {ip} works",
    "arp_test_failed": "❌ ARP CHECK: {device_name} - New IP {ip} doesn't work",
    
    # Connection tests
    "connection_test_start": "🔌 CONNECTION TEST: {device_name} - Testing {ip}",
    "connection_test_success": "✅ CONNECTION TEST: {device_name} - {ip} responds",
    "connection_test_failed": "❌ CONNECTION TEST: {device_name} - {ip} failed: {error}",
    
    # IP changes
    "ip_change_start": "🔄 IP CHANGE: {device_name} - Changing to {new_ip} ({source})",
    "ip_change_success": "✅ IP CHANGE: {device_name} - Successfully changed to {new_ip}",
    "ip_change_failed": "❌ IP CHANGE: {device_name} - Failed to change to {new_ip}: {error}",
    
    # Error tracking
    "error_recorded": "📊 ERROR: {device_name} - {error_type} (consecutive: {count})",
    "error_cascade": "🌊 NETWORK CASCADE: Multiple MaxSmart devices failing",
    "error_recovery": "✅ RECOVERY: {device_name} - Back online after {errors} errors",
    
    # Migration
    "migration_start": "🔄 MIGRATION: {scenario}",
    "migration_success": "✅ MIGRATION: {device_name} - Successfully migrated",
    "migration_failed": "❌ MIGRATION: {device_name} - Failed: {error}",
    
    # Device info
    "device_recreated": "🔧 DEVICE: {device_name} - Firmware={firmware}, Format={format}, Multiplier={multiplier}",
    "config_updated": "📋 CONFIG: {device_name} - Updated {field}: {old} → {new}",
}

# User notification messages
NOTIFICATION_MESSAGES = {
    "ip_changed": {
        "title": "MaxSmart IP Address Updated",
        "message": "Device '{device_name}' IP address updated to {new_ip}. The device will reconnect automatically."
    },
    "migration_complete": {
        "title": "MaxSmart Migration Complete", 
        "message": "Successfully migrated {count} MaxSmart devices to enhanced format."
    },
    "ip_test_failed": {
        "title": "IP Address Test Failed",
        "message": "The new IP address {ip} does not respond. Please verify the address is correct."
    }
}

def log_setup_start(device_name: str, ip: str) -> None:
    """Log setup start."""
    _LOGGER.debug(LOG_MESSAGES["setup_start"].format(device_name=device_name, ip=ip))

def log_setup_success(device_name: str) -> None:
    """Log successful setup."""
    _LOGGER.debug(LOG_MESSAGES["setup_success"].format(device_name=device_name))

def log_setup_failed(device_name: str, error: str) -> None:
    """Log setup failure."""
    _LOGGER.error(LOG_MESSAGES["setup_failed"].format(device_name=device_name, error=error))

def log_ip_recovery_start(device_name: str, old_ip: str, mac: str) -> None:
    """Log IP recovery start."""
    mac_short = mac[:12] + "..." if len(mac) > 12 else mac
    _LOGGER.debug(LOG_MESSAGES["ip_recovery_start"].format(
        device_name=device_name, old_ip=old_ip, mac=mac_short
    ))

def log_ip_recovery_success(device_name: str, old_ip: str, new_ip: str) -> None:
    """Log successful IP recovery."""
    _LOGGER.info(LOG_MESSAGES["ip_recovery_success"].format(
        device_name=device_name, old_ip=old_ip, new_ip=new_ip
    ))

def log_ip_recovery_failed(device_name: str) -> None:
    """Log failed IP recovery."""
    _LOGGER.debug(LOG_MESSAGES["ip_recovery_failed"].format(device_name=device_name))

def log_ip_recovery_exhausted(device_name: str, attempts: int, max_attempts: int) -> None:
    """Log exhausted IP recovery."""
    _LOGGER.warning(LOG_MESSAGES["ip_recovery_exhausted"].format(
        device_name=device_name, attempts=attempts, max_attempts=max_attempts
    ))

def log_arp_check_start(device_name: str) -> None:
    """Log ARP check start."""
    _LOGGER.debug(LOG_MESSAGES["arp_check_start"].format(device_name=device_name))

def log_arp_ip_changed(device_name: str, old_ip: str, new_ip: str) -> None:
    """Log ARP detected IP change."""
    _LOGGER.debug(LOG_MESSAGES["arp_ip_changed"].format(
        device_name=device_name, old_ip=old_ip, new_ip=new_ip
    ))

def log_arp_no_change(device_name: str) -> None:
    """Log ARP no change detected."""
    _LOGGER.debug(LOG_MESSAGES["arp_no_change"].format(device_name=device_name))

def log_connection_test_start(device_name: str, ip: str) -> None:
    """Log connection test start."""
    _LOGGER.debug(LOG_MESSAGES["connection_test_start"].format(device_name=device_name, ip=ip))

def log_connection_test_success(device_name: str, ip: str) -> None:
    """Log successful connection test."""
    _LOGGER.debug(LOG_MESSAGES["connection_test_success"].format(device_name=device_name, ip=ip))

def log_connection_test_failed(device_name: str, ip: str, error: str) -> None:
    """Log failed connection test."""
    _LOGGER.debug(LOG_MESSAGES["connection_test_failed"].format(
        device_name=device_name, ip=ip, error=error
    ))

def log_error_recorded(device_name: str, error_type: str, count: int, should_log: bool = True) -> None:
    """Log error recording with smart filtering."""
    if should_log:
        _LOGGER.warning(LOG_MESSAGES["error_recorded"].format(
            device_name=device_name, error_type=error_type, count=count
        ))

def log_device_recreated(device_name: str, firmware: str, format_type: str, multiplier: float) -> None:
    """Log device recreation info."""
    _LOGGER.debug(LOG_MESSAGES["device_recreated"].format(
        device_name=device_name, firmware=firmware, format=format_type, multiplier=multiplier
    ))

def log_config_raw_before(source: str, data: Dict[str, Any]) -> None:
    """Log raw config data before change."""
    _LOGGER.debug(f"📋 CONFIG RAW BEFORE ({source}): {data}")

def log_config_raw_after(data: Dict[str, Any]) -> None:
    """Log raw config data after change."""
    _LOGGER.debug(f"📋 CONFIG RAW AFTER: {data}")
