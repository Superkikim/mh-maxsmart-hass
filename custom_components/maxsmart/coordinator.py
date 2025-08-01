# custom_components/maxsmart/coordinator.py
"""MaxSmart coordinator using intelligent polling from maxsmart module with dynamic IP recovery."""

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

class MaxSmartCoordinator(DataUpdateCoordinator):
    """Enhanced coordinator using maxsmart intelligent polling system with dynamic IP recovery."""

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
        
        # Error tracking for intelligent logging
        self._consecutive_errors = 0
        self._last_error_type = None
        self._total_errors = 0
        self._successful_polls = 0
        
        # Dynamic IP recovery tracking
        self._ip_recovery_attempted = False
        self._last_ip_recovery_time = 0
        self._last_successful_poll = 0  # Track last successful poll for error detection
        self._error_detection_task = None

    async def _async_setup(self) -> None:
        """Set up the coordinator and initialize device with intelligent polling."""
        if self._initialized:
            return
            
        try:
            _LOGGER.debug("Initializing MaxSmart device with intelligent polling: %s (%s)", 
                         self.device_name, self.device_ip)
            
            self.device = MaxSmartDevice(self.device_ip)
            await self.device.initialize_device()
            
            # 🎯 START INTELLIGENT POLLING with IP recovery callback
            await self.device.start_adaptive_polling(enable_burst=True)
            
            # Register single polling callback for real-time data updates
            self.device.register_poll_callback("coordinator", self._on_poll_data)
            
            # Start error detection timer for IP recovery
            self._start_error_detection()
            
            self._initialized = True
            self._consecutive_errors = 0
            self._polling_failures = 0
            
            # Log successful initialization
            hw_info = self._format_hardware_info()
            _LOGGER.info("MaxSmart device ready with intelligent polling: %s (%s)%s", 
                        self.device_name, self.device_ip, hw_info)
            
        except (DiscoveryError, MaxSmartConnectionError) as err:
            error_msg = f"Cannot connect to MaxSmart device {self.device_name} ({self.device_ip}): {err}"
            _LOGGER.error(error_msg)
            raise UpdateFailed(error_msg)
                
        except Exception as err:
            error_msg = f"Unexpected error initializing {self.device_name}: {err}"
            _LOGGER.error(error_msg)
            raise UpdateFailed(error_msg)

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
            self._last_successful_poll = time.time()  # Update last successful poll time
            
            # Log recovery from errors
            if self._consecutive_errors > 0:
                recovery_info = ""
                if self._ip_recovery_attempted:
                    recovery_info = " (IP recovery successful)"
                    
                _LOGGER.info("MaxSmart device %s recovered after %d failed polls%s", 
                           self.device_name, self._consecutive_errors, recovery_info)
                self._consecutive_errors = 0
                self._last_error_type = None
                
            # Periodic success logging
            if self._successful_polls % 100 == 0:
                _LOGGER.debug("MaxSmart intelligent polling: %s - %d successful polls, %d errors (mode: %s)", 
                            self.device_name, self._successful_polls, self._total_errors, mode)
            
            # 🎯 UPDATE HA COORDINATOR DATA - This triggers entity updates
            self.async_set_updated_data(device_data)
            
        except Exception as err:
            _LOGGER.error("Error processing poll data for %s: %s", self.device_name, err)

    def _start_error_detection(self) -> None:
        """Start background task to detect polling errors by timeout."""
        if self._error_detection_task:
            self._error_detection_task.cancel()
            
        self._error_detection_task = asyncio.create_task(self._error_detection_loop())

    async def _error_detection_loop(self) -> None:
        """Background loop to detect when polling stops working."""
        try:
            while self._initialized:
                await asyncio.sleep(20)  # Check every 20 seconds
                
                current_time = time.time()
                time_since_last_poll = current_time - self._last_successful_poll
                
                # If no successful poll for 30 seconds, consider it an error
                if time_since_last_poll > 30 and self._last_successful_poll > 0:
                    _LOGGER.warning("No polls received for %.0fs from device %s, attempting IP recovery", 
                                  time_since_last_poll, self.device_name)
                    
                    # Attempt IP recovery
                    if await self._should_attempt_ip_recovery():
                        new_ip = await self._recover_device_ip()
                        if new_ip:
                            await self._update_device_ip(new_ip)
                            await self._restart_polling_with_new_ip(new_ip)
                            
        except asyncio.CancelledError:
            pass
        except Exception as err:
            _LOGGER.error("Error detection loop failed for %s: %s", self.device_name, err)

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
            
            # Reset counters
            self._consecutive_errors = 0
            self._last_successful_poll = time.time()
            
            _LOGGER.info("IP recovery successful for %s, intelligent polling restarted with new IP %s", 
                       self.device_name, new_ip)
                       
        except Exception as err:
            _LOGGER.error("Failed to restart polling with new IP for %s: %s", self.device_name, err)

    async def _async_update_data(self) -> Dict[str, Any]:
        """
        Fallback update method - should rarely be called since we use intelligent polling.
        This is only used if intelligent polling fails completely.
        """
        if not self._initialized:
            await self._async_setup()
            return {}
            
        try:
            _LOGGER.debug("Fallback polling for %s (intelligent polling may have failed)", self.device_name)
            
            data = await self.device.get_data()
            return data
            
        except Exception as err:
            _LOGGER.error("Fallback polling failed for %s: %s", self.device_name, err)
            raise UpdateFailed(f"Device {self.device_name} unreachable: {err}")

    async def _should_attempt_ip_recovery(self) -> bool:
        """Determine if we should attempt IP recovery."""
        if not self.mac_address:
            return False
            
        current_time = time.time()
        if self._ip_recovery_attempted and (current_time - self._last_ip_recovery_time) < 300:
            return False
            
        return True

    async def _recover_device_ip(self) -> Optional[str]:
        """Attempt to recover device IP using MAC address lookup."""
        if not self.mac_address:
            return None
            
        self._ip_recovery_attempted = True
        self._last_ip_recovery_time = time.time()
        
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

    def _should_log_error(self, error_type: str) -> bool:
        """Determine if an error should be logged."""
        if self._consecutive_errors <= 3:
            return True
            
        if error_type != self._last_error_type:
            return True
            
        if error_type in ["ConnectionError", "TimeoutError", "MaxSmartConnectionError"]:
            return self._consecutive_errors % 10 == 0
            
        return self._consecutive_errors % 5 == 0

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
            await self._async_setup()
            
        try:
            _LOGGER.debug("Turning on port %d for %s", port_id, self.device_name)
            
            await self.device.turn_on(port_id)  # This triggers burst mode automatically
            _LOGGER.debug("Port %d turned on successfully for %s - burst mode activated", 
                         port_id, self.device_name)
            return True
            
        except Exception as err:
            _LOGGER.warning("Failed to turn on port %d for %s: %s", port_id, self.device_name, err)
            return False

    async def async_turn_off(self, port_id: int) -> bool:
        """Turn off a port - triggers burst mode in intelligent polling."""
        if not self._initialized:
            await self._async_setup()
            
        try:
            _LOGGER.debug("Turning off port %d for %s", port_id, self.device_name)
            
            await self.device.turn_off(port_id)  # This triggers burst mode automatically
            _LOGGER.debug("Port %d turned off successfully for %s - burst mode activated", 
                         port_id, self.device_name)
            return True
            
        except Exception as err:
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
                
                # Intelligent polling statistics
                "polling_system": "maxsmart_intelligent",
                "polling_active": self.device.is_polling if self.device else False,
                "successful_polls": self._successful_polls,
                "total_errors": self._total_errors,
                "last_successful_poll": self._last_successful_poll,
                
                # IP recovery info
                "supports_ip_recovery": bool(self.mac_address),
                "ip_recovery_attempted": self._ip_recovery_attempted,
                "last_ip_recovery_time": self._last_ip_recovery_time,
            }
            
            # IP recovery status
            if self.mac_address:
                base_info["ip_recovery_status"] = "Available (MAC address known)"
            else:
                base_info["ip_recovery_status"] = "Not available (no MAC address)"
            
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