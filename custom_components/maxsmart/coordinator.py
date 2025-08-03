# custom_components/maxsmart/coordinator.py
"""MaxSmart coordinator with intelligent polling and smart error handling."""

from __future__ import annotations

import asyncio
import logging
import platform
import re
import subprocess
import time
from datetime import timedelta
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.config_entries import ConfigEntry

from maxsmart import MaxSmartDevice, MaxSmartDiscovery
from maxsmart.exceptions import (
    ConnectionError as MaxSmartConnectionError,
    CommandError,
    DeviceTimeoutError,
    DiscoveryError,
)

_LOGGER = logging.getLogger(__name__)

# Disable HA polling - we use maxsmart intelligent polling instead
UPDATE_INTERVAL = timedelta(seconds=300)  # Very long interval as fallback only

class NetworkCascadeDetector:
    """Detects network cascade failures to reduce log pollution."""
    
    _instance = None
    _cascade_devices = set()
    _cascade_start_time = None
    _cascade_logged = False
    _cascade_threshold = 3  # 3+ devices failing = cascade
    _cascade_window = 30  # within 30 seconds
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def report_device_failure(cls, device_name: str) -> bool:
        """
        Report device failure and return if it should be logged.
        
        Returns:
            True if this failure should be logged individually
        """
        current_time = time.time()
        detector = cls()
        
        # Clean old cascade data
        if (detector._cascade_start_time and 
            current_time - detector._cascade_start_time > cls._cascade_window * 2):
            detector._reset_cascade()
        
        # Add device to cascade
        detector._cascade_devices.add(device_name)
        
        if detector._cascade_start_time is None:
            detector._cascade_start_time = current_time
        
        # Check for cascade
        if len(detector._cascade_devices) >= cls._cascade_threshold:
            if not detector._cascade_logged:
                detector._cascade_logged = True
                _LOGGER.warning("Network cascade detected: %d MaxSmart devices offline (possible powerlan/network issue)", 
                               len(detector._cascade_devices))
                return False  # Don't log individual errors during cascade
            return False  # Cascade already logged
        
        # Less than threshold, log individual error
        return True
    
    @classmethod
    def report_device_recovery(cls, device_name: str) -> bool:
        """
        Report device recovery and return if cascade recovery should be logged.
        
        Returns:
            True if cascade recovery should be logged
        """
        detector = cls()
        
        if device_name in detector._cascade_devices:
            detector._cascade_devices.remove(device_name)
            
            # Check if cascade is ending
            if detector._cascade_logged and len(detector._cascade_devices) <= 1:
                detector._reset_cascade()
                return True  # Log cascade recovery
                
        return False
    
    def _reset_cascade(self):
        """Reset cascade state."""
        self._cascade_devices.clear()
        self._cascade_start_time = None
        self._cascade_logged = False

class SmartErrorTracker:
    """Smart error tracking to prevent log pollution and manage recovery intelligently."""
    
    def __init__(self, device_name: str):
        """Initialize smart error tracker."""
        self.device_name = device_name
        
        # Error state tracking
        self.consecutive_errors = 0
        self.total_errors = 0
        self.last_error_type = None
        self.first_error_time = None
        self.last_successful_poll = time.time()
        
        # IP recovery tracking
        self.ip_recovery_attempts = 0
        self.max_ip_recovery_attempts = 3
        self.last_ip_recovery_time = 0
        self.ip_recovery_cooldown = 300  # 5 minutes between attempts
        self.ip_recovery_exhausted = False
        
        # Smart logging
        self.last_warning_time = 0
        self.warning_interval = 300  # 5 minutes between warnings
        self.error_silence_after = 600  # Stop logging after 10 minutes of errors
        
        # Network cascade awareness
        self.in_cascade = False
        
    def record_successful_poll(self) -> None:
        """Record a successful poll - resets error state."""
        had_errors = self.consecutive_errors > 0
        
        self.consecutive_errors = 0
        self.last_error_type = None
        self.first_error_time = None
        self.last_successful_poll = time.time()
        
        # Check for cascade recovery
        if had_errors:
            cascade_recovery = NetworkCascadeDetector.report_device_recovery(self.device_name)
            if cascade_recovery:
                _LOGGER.info("Network cascade resolved - MaxSmart devices coming back online")
            elif not self.in_cascade:
                _LOGGER.info("%s recovered successfully", self.device_name)
        
        # Reset IP recovery state on successful connection
        if had_errors and self.ip_recovery_attempts > 0:
            self.ip_recovery_attempts = 0
            self.ip_recovery_exhausted = False
            
        self.in_cascade = False
    
    def record_error(self, error_type: str) -> bool:
        """
        Record an error and return whether it should be logged.
        
        Returns:
            True if this error should be logged
        """
        current_time = time.time()
        
        self.consecutive_errors += 1
        self.total_errors += 1
        
        if self.first_error_time is None:
            self.first_error_time = current_time
            
        self.last_error_type = error_type
        
        # Check for network cascade
        if error_type in ["connection_refused", "setup_failed", "polling_timeout"]:
            should_log_cascade = NetworkCascadeDetector.report_device_failure(self.device_name)
            if not should_log_cascade:
                self.in_cascade = True
                return False  # Don't log individual errors during cascade
        
        # Smart logging logic for individual errors
        should_log = self._should_log_error(current_time)
        return should_log
    
    def _should_log_error(self, current_time: float) -> bool:
        """Determine if an error should be logged to prevent spam."""
        # Always log first error
        if self.consecutive_errors == 1:
            return True
            
        # Always log if error type changed
        if self.last_error_type != self.last_error_type:
            return True
            
        # Stop logging after prolonged errors
        if self.first_error_time and (current_time - self.first_error_time) > self.error_silence_after:
            return False
            
        # Log every 5 minutes for connection errors
        if (current_time - self.last_warning_time) >= self.warning_interval:
            self.last_warning_time = current_time
            return True
            
        return False
    
    def should_attempt_ip_recovery(self) -> bool:
        """Determine if IP recovery should be attempted."""
        current_time = time.time()
        
        # Don't attempt if exhausted
        if self.ip_recovery_exhausted:
            return False
            
        # Don't attempt if max attempts reached
        if self.ip_recovery_attempts >= self.max_ip_recovery_attempts:
            self.ip_recovery_exhausted = True
            _LOGGER.warning("%s IP recovery exhausted (%d attempts), giving up", 
                          self.device_name, self.max_ip_recovery_attempts)
            return False
            
        # Don't attempt if in cooldown
        if (current_time - self.last_ip_recovery_time) < self.ip_recovery_cooldown:
            return False
            
        # Only attempt after sustained errors (2+ minutes)
        if self.first_error_time and (current_time - self.first_error_time) < 120:
            return False
            
        return True
    
    def start_ip_recovery_attempt(self) -> None:
        """Record the start of an IP recovery attempt."""
        self.ip_recovery_attempts += 1
        self.last_ip_recovery_time = time.time()
        
        _LOGGER.info("%s starting IP recovery attempt %d/%d", 
                    self.device_name, self.ip_recovery_attempts, self.max_ip_recovery_attempts)
    
    def is_device_considered_offline(self) -> bool:
        """Check if device should be considered offline (for error detection)."""
        current_time = time.time()
        time_since_last_poll = current_time - self.last_successful_poll
        
        # Consider offline after 60 seconds without successful poll
        return time_since_last_poll > 60 and self.last_successful_poll > 0
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get status summary for diagnostics."""
        current_time = time.time()
        return {
            "consecutive_errors": self.consecutive_errors,
            "total_errors": self.total_errors,
            "last_error_type": self.last_error_type,
            "time_since_last_success": current_time - self.last_successful_poll if self.last_successful_poll > 0 else None,
            "ip_recovery_attempts": self.ip_recovery_attempts,
            "ip_recovery_exhausted": self.ip_recovery_exhausted,
            "considered_offline": self.is_device_considered_offline(),
        }

class MaxSmartCoordinator(DataUpdateCoordinator):
    """Enhanced coordinator with intelligent polling and smart error handling."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator with intelligent polling."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"MaxSmart {config_entry.data['device_name']}",
            update_interval=UPDATE_INTERVAL,  # Long fallback interval
        )
        
        self.config_entry = config_entry
        self.device_ip = config_entry.data["device_ip"]
        self.device_name = config_entry.data["device_name"]
        self.device_unique_id = config_entry.data["device_unique_id"]
        
        # Enhanced device information
        self.cpu_id = config_entry.data.get("cpu_id", "")
        self.mac_address = config_entry.data.get("mac_address", "")
        self.identification_method = config_entry.data.get("identification_method", "fallback")
        
        self.device: Optional[MaxSmartDevice] = None
        self._initialized = False
        
        # Smart error tracking
        self.error_tracker = SmartErrorTracker(self.device_name)
        
        # Polling statistics
        self._successful_polls = 0
        
        # Error detection task with longer intervals
        self._error_detection_task = None

    async def _async_setup(self) -> None:
        """Set up the coordinator and initialize device with intelligent polling and resilient setup."""
        if self._initialized:
            return
            
        try:
            _LOGGER.debug("Initializing MaxSmart device with intelligent polling: %s (%s)", 
                         self.device_name, self.device_ip)
            
            self.device = MaxSmartDevice(self.device_ip)
            await self.device.initialize_device()
            
            # Start intelligent polling with burst mode
            await self.device.start_adaptive_polling(enable_burst=True)
            
            # Register single polling callback for real-time data updates
            self.device.register_poll_callback("coordinator", self._on_poll_data)
            
            # Start smart error detection with longer intervals
            self._start_smart_error_detection()
            
            self._initialized = True
            
            # Log successful initialization
            hw_info = self._format_hardware_info()
            _LOGGER.info("MaxSmart device ready with intelligent polling: %s (%s)%s", 
                        self.device_name, self.device_ip, hw_info)
            
        except (DiscoveryError, MaxSmartConnectionError) as err:
            # Smart cascade-aware error logging
            should_log = self.error_tracker.record_error("setup_failed")
            
            if should_log:
                _LOGGER.error("Cannot connect to MaxSmart device %s (%s): %s", 
                            self.device_name, self.device_ip, err)
            
            # Create resilient setup - integration loads but device unavailable
            _LOGGER.info("Creating resilient setup for offline device: %s", self.device_name)
            self._initialized = False  # Mark as not initialized but don't fail
            
            # Start periodic retry for offline devices
            self._start_offline_retry()
            
            # Don't raise UpdateFailed - let integration load in unavailable state
            return
                
        except Exception as err:
            should_log = self.error_tracker.record_error("setup_error")
            
            if should_log:
                _LOGGER.error("Unexpected error initializing %s: %s", self.device_name, err)
                
            raise UpdateFailed(f"Setup failed for {self.device_name}: {err}")

    async def _on_poll_data(self, poll_data: Dict[str, Any]) -> None:
        """
        Callback for successful polling data from maxsmart intelligent polling.
        This replaces the traditional HA polling mechanism.
        """
        try:
            device_data = poll_data.get("device_data", {})
            poll_count = poll_data.get("poll_count", 0)
            mode = poll_data.get("mode", "unknown")
            
            # Track successful poll
            self._successful_polls += 1
            self.error_tracker.record_successful_poll()
            
            # Periodic success logging (much less frequent)
            if self._successful_polls % 200 == 0:  # Every 200 polls instead of 100
                _LOGGER.debug("MaxSmart intelligent polling: %s - %d successful polls, %d errors (mode: %s)", 
                            self.device_name, self._successful_polls, self.error_tracker.total_errors, mode)
            
            # Update HA coordinator data - This triggers entity updates
            self.async_set_updated_data(device_data)
            
        except Exception as err:
            _LOGGER.error("Error processing poll data for %s: %s", self.device_name, err)

    def _start_offline_retry(self) -> None:
        """Start periodic retry for offline devices."""
        if self._error_detection_task:
            self._error_detection_task.cancel()
            
        self._error_detection_task = asyncio.create_task(self._offline_retry_loop())

    async def _offline_retry_loop(self) -> None:
        """Periodic retry loop for offline devices."""
        try:
            retry_interval = 60  # Start with 1 minute
            max_interval = 300   # Max 5 minutes
            
            while not self._initialized:
                await asyncio.sleep(retry_interval)
                
                try:
                    _LOGGER.debug("Attempting to reconnect offline device: %s", self.device_name)
                    
                    self.device = MaxSmartDevice(self.device_ip)
                    await self.device.initialize_device()
                    
                    # Start intelligent polling
                    await self.device.start_adaptive_polling(enable_burst=True)
                    self.device.register_poll_callback("coordinator", self._on_poll_data)
                    
                    # Start normal error detection
                    self._start_smart_error_detection()
                    
                    self._initialized = True
                    
                    # Record successful recovery
                    self.error_tracker.record_successful_poll()
                    
                    _LOGGER.info("Successfully reconnected offline device: %s", self.device_name)
                    return
                    
                except Exception:
                    # Increase retry interval up to max
                    retry_interval = min(retry_interval * 1.5, max_interval)
                    continue
                    
        except asyncio.CancelledError:
            pass
        except Exception as err:
            _LOGGER.error("Offline retry loop failed for %s: %s", self.device_name, err)
    def _start_smart_error_detection(self) -> None:
        """Start background task with smart error detection intervals."""
        if self._error_detection_task:
            self._error_detection_task.cancel()
            
        self._error_detection_task = asyncio.create_task(self._smart_error_detection_loop())

    async def _smart_error_detection_loop(self) -> None:
        """Smart error detection loop with intelligent intervals and recovery."""
        try:
            while self._initialized:
                await asyncio.sleep(60)  # Check every minute instead of 20 seconds
                
                # Check if device is considered offline
                if self.error_tracker.is_device_considered_offline():
                    
                    # Record error for smart logging
                    should_log = self.error_tracker.record_error("polling_timeout")
                    
                    if should_log:
                        time_offline = time.time() - self.error_tracker.last_successful_poll
                        _LOGGER.warning("%s has been offline for %.0f seconds, checking connectivity", 
                                      self.device_name, time_offline)
                    
                    # Attempt IP recovery if conditions are met
                    if self.error_tracker.should_attempt_ip_recovery():
                        await self._attempt_smart_ip_recovery()
                        
                else:
                    # Device is responding normally, no action needed
                    pass
                    
        except asyncio.CancelledError:
            pass
        except Exception as err:
            _LOGGER.error("Smart error detection loop failed for %s: %s", self.device_name, err)

    async def _attempt_smart_ip_recovery(self) -> None:
        """Attempt intelligent IP recovery with proper tracking."""
        if not self.mac_address:
            _LOGGER.debug("%s has no MAC address, cannot attempt IP recovery", self.device_name)
            return
            
        self.error_tracker.start_ip_recovery_attempt()
        
        try:
            new_ip = await self._recover_device_ip()
            if new_ip and new_ip != self.device_ip:
                _LOGGER.info("%s IP recovery found new address: %s -> %s", 
                           self.device_name, self.device_ip, new_ip)
                await self._update_device_ip(new_ip)
                await self._restart_polling_with_new_ip(new_ip)
            else:
                _LOGGER.debug("%s IP recovery attempt %d failed - no new IP found", 
                            self.device_name, self.error_tracker.ip_recovery_attempts)
                
        except Exception as err:
            _LOGGER.warning("%s IP recovery attempt %d failed: %s", 
                          self.device_name, self.error_tracker.ip_recovery_attempts, err)

    async def _restart_polling_with_new_ip(self, new_ip: str) -> None:
        """Restart intelligent polling with new IP address."""
        try:
            # Stop current polling
            await self.device.stop_adaptive_polling()
            
            # Create new device instance with new IP
            self.device = MaxSmartDevice(new_ip)
            await self.device.initialize_device()
            
            # Restart polling
            await self.device.start_adaptive_polling(enable_burst=True)
            self.device.register_poll_callback("coordinator", self._on_poll_data)
            
            _LOGGER.info("%s IP recovery successful, intelligent polling restarted with new IP %s", 
                       self.device_name, new_ip)
                       
        except Exception as err:
            _LOGGER.error("%s failed to restart polling with new IP: %s", self.device_name, err)

    async def _async_update_data(self) -> Dict[str, Any]:
        """
        Fallback update method for offline devices or when intelligent polling fails.
        """
        # For offline devices, return empty data to keep entities in unavailable state
        if not self._initialized:
            return {}
            
        try:
            # Record this as a fallback attempt
            should_log = self.error_tracker.record_error("fallback_polling")
            
            if should_log:
                _LOGGER.warning("%s using fallback polling (intelligent polling may have failed)", self.device_name)
            
            data = await self.device.get_data()
            
            # If fallback succeeds, record it
            self.error_tracker.record_successful_poll()
            return data
            
        except Exception as err:
            should_log = self.error_tracker.record_error("fallback_failed")
            
            if should_log and not self.error_tracker.in_cascade:
                _LOGGER.error("%s fallback polling failed: %s", self.device_name, err)
                
            # Return empty data instead of raising UpdateFailed to keep integration loaded
            return {}

    async def _recover_device_ip(self) -> Optional[str]:
        """Attempt to recover device IP using MAC address lookup."""
        if not self.mac_address:
            return None
            
        _LOGGER.debug("Starting IP recovery for device %s with MAC %s", self.device_name, self.mac_address)
        
        # Method 1: ARP table lookup
        new_ip = await self._get_ip_from_arp_table(self.mac_address)
        if new_ip:
            return new_ip
            
        # Method 2: Ping subnet + ARP retry
        await self._ping_subnet_to_populate_arp()
        new_ip = await self._get_ip_from_arp_table(self.mac_address)
        if new_ip:
            return new_ip
            
        # Method 3: Discovery fallback
        new_ip = await self._find_device_via_discovery()
        if new_ip:
            return new_ip
            
        return None

    async def _get_ip_from_arp_table(self, mac_address: str) -> Optional[str]:
        """Get IP address from system ARP table by MAC address."""
        try:
            if platform.system().lower() == "windows":
                cmd = ["arp", "-a"]
            else:
                cmd = ["arp", "-a"]
                
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                return None
                
            arp_output = stdout.decode()
            mac_clean = mac_address.lower().replace(':', '-')
            mac_colon = mac_address.lower().replace('-', ':')
            
            for line in arp_output.split('\n'):
                line_lower = line.lower()
                if mac_clean in line_lower or mac_colon in line_lower:
                    ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                    if ip_match:
                        found_ip = ip_match.group(1)
                        if found_ip != self.device_ip:
                            return found_ip
                            
        except Exception as e:
            _LOGGER.debug("Error reading ARP table: %s", e)
            
        return None

    async def _ping_subnet_to_populate_arp(self) -> None:
        """Ping subnet to populate ARP table."""
        try:
            subnet_base = '.'.join(self.device_ip.split('.')[:-1])
            broadcast_ip = f"{subnet_base}.255"
            
            if platform.system().lower() == "windows":
                cmd = ["ping", "-n", "1", "-w", "1000", broadcast_ip]
            else:
                cmd = ["ping", "-c", "1", "-W", "1", broadcast_ip]
                
            await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            
            await asyncio.sleep(0.5)
            
        except Exception as e:
            _LOGGER.debug("Error pinging subnet: %s", e)

    async def _find_device_via_discovery(self) -> Optional[str]:
        """Find device via discovery using MAC matching."""
        try:
            devices = await MaxSmartDiscovery.discover_maxsmart(enhance_with_hardware_ids=True)
            
            for device in devices:
                device_mac = device.get("mac_address") or device.get("pclmac", "")
                if device_mac and self._normalize_mac(device_mac) == self._normalize_mac(self.mac_address):
                    return device.get("ip")
                    
            # Fallback: CPU ID match
            if self.cpu_id:
                for device in devices:
                    if device.get("cpuid") == self.cpu_id:
                        return device.get("ip")
                        
        except Exception as e:
            _LOGGER.debug("Discovery fallback failed: %s", e)
            
        return None

    def _normalize_mac(self, mac: str) -> str:
        """Normalize MAC address for comparison."""
        return mac.lower().replace(':', '').replace('-', '')

    async def _update_device_ip(self, new_ip: str) -> None:
        """Update device IP in config entry."""
        try:
            new_data = dict(self.config_entry.data)
            new_data["device_ip"] = new_ip
            
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data
            )
            
            self.device_ip = new_ip
            _LOGGER.info("Updated device %s IP address to %s", self.device_name, new_ip)
            
        except Exception as e:
            _LOGGER.error("Failed to update device IP for %s: %s", self.device_name, e)

    def _format_hardware_info(self) -> str:
        """Format hardware information for logging."""
        hw_parts = []
        
        if self.identification_method and self.identification_method != "fallback":
            hw_parts.append(f"ID: {self.identification_method.replace('_', ' ').title()}")
            
        if self.cpu_id:
            hw_parts.append(f"CPU: {self.cpu_id[:8]}...")
            
        if self.mac_address:
            hw_parts.append(f"MAC: {self.mac_address}")
            
        return f" [{', '.join(hw_parts)}]" if hw_parts else ""

    async def async_turn_on(self, port_id: int) -> bool:
        """Turn on a port - triggers burst mode in intelligent polling."""
        if not self._initialized:
            _LOGGER.warning("Cannot turn on port %d for %s - device offline", port_id, self.device_name)
            return False
            
        try:
            _LOGGER.debug("Turning on port %d for %s", port_id, self.device_name)
            
            await self.device.turn_on(port_id)  # This triggers burst mode automatically
            _LOGGER.debug("Port %d turned on successfully for %s - burst mode activated", 
                         port_id, self.device_name)
            return True
            
        except Exception as err:
            should_log = self.error_tracker.record_error("command_failed")
            if should_log and not self.error_tracker.in_cascade:
                _LOGGER.warning("Failed to turn on port %d for %s: %s", port_id, self.device_name, err)
            return False

    async def async_turn_off(self, port_id: int) -> bool:
        """Turn off a port - triggers burst mode in intelligent polling."""
        if not self._initialized:
            _LOGGER.warning("Cannot turn off port %d for %s - device offline", port_id, self.device_name)
            return False
            
        try:
            _LOGGER.debug("Turning off port %d for %s", port_id, self.device_name)
            
            await self.device.turn_off(port_id)  # This triggers burst mode automatically
            _LOGGER.debug("Port %d turned off successfully for %s - burst mode activated", 
                         port_id, self.device_name)
            return True
            
        except Exception as err:
            should_log = self.error_tracker.record_error("command_failed")
            if should_log and not self.error_tracker.in_cascade:
                _LOGGER.warning("Failed to turn off port %d for %s: %s", port_id, self.device_name, err)
            return False

    async def async_get_device_info(self) -> Dict[str, Any]:
        """Get comprehensive device information for diagnostics."""
        if not self._initialized:
            await self._async_setup()
            
        try:
            base_info = {
                "name": self.device_name,
                "ip": self.device_ip,
                "unique_id": self.device_unique_id,
                "coordinator_name": self.name,
                "initialized": self._initialized,
                
                # Enhanced identification
                "cpu_id": self.cpu_id,
                "mac_address": self.mac_address,
                "identification_method": self.identification_method,
                
                # Smart polling statistics
                "polling_system": "maxsmart_intelligent",
                "polling_active": self.device.is_polling if self.device else False,
                "successful_polls": self._successful_polls,
                
                # Smart error tracking
                "error_tracker": self.error_tracker.get_status_summary(),
                
                # IP recovery info
                "supports_ip_recovery": bool(self.mac_address),
            }
            
            # Add device-specific info if available
            if self.device:
                try:
                    device_specific = {
                        "firmware": getattr(self.device, 'version', 'Unknown'),
                        "data_format": getattr(self.device, '_watt_format', 'Unknown'),
                        "conversion_factor": getattr(self.device, '_watt_multiplier', 1.0),
                    }
                    base_info.update(device_specific)
                    
                except Exception as err:
                    base_info["device_info_error"] = str(err)
                    
            return base_info
            
        except Exception as err:
            _LOGGER.error("Error getting device info for %s: %s", self.device_name, err)
            return {"error": str(err)}

    async def async_reload_from_config(self) -> None:
        """Reload coordinator when config entry is updated."""
        _LOGGER.info("Reloading coordinator for %s due to config change", self.device_name)
        
        self.device_name = self.config_entry.data["device_name"]
        self.name = f"MaxSmart {self.device_name}"
        
        new_ip = self.config_entry.data["device_ip"]
        if new_ip != self.device_ip:
            _LOGGER.info("Device IP updated in config: %s → %s", self.device_ip, new_ip)
            self.device_ip = new_ip
            
            # Restart intelligent polling with new IP
            if self.device:
                await self.device.stop_adaptive_polling()
                await self.device.close()
                
            self.device = None
            self._initialized = False
            
            # Cancel error detection task
            if self._error_detection_task:
                self._error_detection_task.cancel()
                
            # Reset error tracker
            self.error_tracker = SmartErrorTracker(self.device_name)
                
            await self._async_setup()

    async def async_shutdown(self) -> None:
        """Shutdown coordinator with intelligent polling cleanup."""
        _LOGGER.debug("Shutting down coordinator with intelligent polling for %s", self.device_name)
        
        if self.device:
            try:
                # Stop intelligent polling
                await self.device.stop_adaptive_polling()
                await self.device.close()
                _LOGGER.debug("Intelligent polling stopped and device connection closed: %s", self.device_ip)
            except Exception as err:
                _LOGGER.warning("Error shutting down device for %s: %s", self.device_name, err)
        
        # Cancel error detection task
        if self._error_detection_task:
            self._error_detection_task.cancel()
        
        self._initialized = False
        self.device = None