"""IP recovery and network discovery for MaxSmart devices."""

import asyncio
import logging
import platform
import re
import time
from typing import Dict, Any, Optional

from maxsmart import MaxSmartDevice

from ..messages import (
    log_arp_check_start, log_arp_ip_changed,
    log_connection_test_start, log_connection_test_success, log_connection_test_failed,
    log_config_raw_before, log_config_raw_after
)

_LOGGER = logging.getLogger(__name__)


class ConservativeIPRecovery:
    """Conservative IP recovery with escalating timeline: 10min, 30min, 60min, abandon."""
    
    def __init__(self, device_name: str, mac_address: str):
        """Initialize conservative IP recovery with escalating timeline."""
        self.device_name = device_name
        self.mac_address = mac_address
        self.attempts = 0
        self.max_attempts = 3
        self.last_attempt_time = 0
        self.device_offline_start = None
        
        # Escalating timeline: 10min, 30min, 60min
        self.attempt_intervals = [600, 1800, 3600]  # seconds
        
    def set_device_offline_start(self, offline_time: float) -> None:
        """Set when the device first went offline (for timeline calculation)."""
        if self.device_offline_start is None:
            self.device_offline_start = offline_time
            
    def can_attempt_recovery(self, current_time: float) -> bool:
        """Check if IP recovery can be attempted based on escalating timeline."""
        # Check if we've exhausted all attempts
        if self.attempts >= self.max_attempts:
            return False
        
        # Check if device has been offline long enough for next attempt
        if self.device_offline_start is None:
            return False
        
        time_offline = current_time - self.device_offline_start
        required_time = self.attempt_intervals[self.attempts]
        
        if time_offline < required_time:
            return False
        
        # Check cooldown between attempts (minimum 5 minutes)
        if self.last_attempt_time > 0:
            time_since_last = current_time - self.last_attempt_time
            if time_since_last < 300:  # 5 minutes cooldown
                return False
        
        return True
    
    def start_attempt(self, current_time: float) -> None:
        """Record the start of an IP recovery attempt."""
        self.attempts += 1
        self.last_attempt_time = current_time
        
        _LOGGER.debug("🔍 IP RECOVERY: %s - Starting attempt %d/%d (offline for %.1f min)",
                     self.device_name, self.attempts, self.max_attempts,
                     (current_time - self.device_offline_start) / 60 if self.device_offline_start else 0)
    
    def reset_on_success(self) -> None:
        """Reset attempts counter on successful connection."""
        _LOGGER.debug("✅ IP RECOVERY: %s - Reset after successful recovery", self.device_name)
        self.attempts = 0
        self.last_attempt_time = 0
        self.device_offline_start = None
    
    def get_status(self) -> Dict[str, Any]:
        """Get recovery status for diagnostics."""
        current_time = time.time()
        
        if self.device_offline_start:
            time_offline = current_time - self.device_offline_start
            if self.attempts < self.max_attempts:
                required_time = self.attempt_intervals[self.attempts]
                next_attempt_time = self.device_offline_start + required_time
            else:
                next_attempt_time = None
        else:
            next_attempt_time = None
        
        return {
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "time_offline": current_time - self.device_offline_start if self.device_offline_start else None,
            "next_attempt_in": max(0, next_attempt_time - current_time) if next_attempt_time else None,
            "can_attempt": self.can_attempt_recovery(current_time),
        }


class IPRecoveryManager:
    """Manages IP recovery operations for MaxSmart devices."""
    
    def __init__(self, coordinator):
        """Initialize IP recovery manager."""
        self.coordinator = coordinator
        self.device_name = coordinator.device_name
        self.mac_address = coordinator.mac_address
        self.device_ip = coordinator.device_ip
        self.hass = coordinator.hass
        self.config_entry = coordinator.config_entry
    
    async def immediate_arp_check(self) -> None:
        """Immediate ARP check on every connection failure - lightweight IP recovery."""
        try:
            log_arp_check_start(self.device_name)

            # Step 1: Quick ARP lookup using MAC from config_entry
            new_ip = await self._get_ip_from_arp_table(self.mac_address)

            if new_ip and new_ip != self.device_ip:
                log_arp_ip_changed(self.device_name, self.device_ip, new_ip)

                # Test connection to new IP
                connection_test = await self._try_connect_at_ip(new_ip)
                if connection_test:
                    # Use common method for IP change
                    await self._change_device_ip(new_ip, "arp_recovery")
                    # Complete setup to exit retry loop
                    await self.coordinator._complete_successful_setup()
                    return
                else:
                    _LOGGER.debug("🔍 ARP: %s - New IP %s found but doesn't respond", 
                                 self.device_name, new_ip)
            else:
                _LOGGER.debug("🔍 ARP: %s - No new IP found in ARP table", self.device_name)

            # Step 2: ARP failed or same IP - try discovery as fallback
            _LOGGER.debug("🔍 ARP: %s - Falling back to discovery", self.device_name)
            await self._discovery_fallback()

        except Exception as e:
            _LOGGER.debug("🔍 ARP: %s - Exception: %s", self.device_name, e)

    async def _discovery_fallback(self) -> None:
        """Discovery fallback when ARP fails - find device by MAC comparison."""
        try:
            from ..discovery import async_discover_devices
            
            _LOGGER.debug("🔍 DISCOVERY FALLBACK: %s - Starting discovery", self.device_name)
            
            # Discover all devices on network
            devices = await async_discover_devices(enhance_with_hardware=True)
            
            if not devices:
                _LOGGER.debug("🔍 DISCOVERY FALLBACK: %s - No devices found", self.device_name)
                return
            
            # Find device with matching MAC
            target_mac = self.mac_address.lower().replace(":", "").replace("-", "")
            
            for device in devices:
                device_mac = device.get("mac") or device.get("pclmac", "")
                if device_mac:
                    device_mac_clean = device_mac.lower().replace(":", "").replace("-", "")
                    if device_mac_clean == target_mac:
                        new_ip = device.get("ip")
                        if new_ip and new_ip != self.device_ip:
                            _LOGGER.debug("🔍 DISCOVERY FALLBACK: %s - Found device at %s", 
                                         self.device_name, new_ip)
                            
                            # Test connection to new IP
                            connection_test = await self._try_connect_at_ip(new_ip)
                            if connection_test:
                                await self._change_device_ip(new_ip, "discovery_recovery")
                                # Complete setup to exit retry loop
                                await self.coordinator._complete_successful_setup()
                                return
                        else:
                            _LOGGER.debug("🔍 DISCOVERY FALLBACK: %s - Same IP %s found", 
                                         self.device_name, new_ip)
            
            _LOGGER.debug("🔍 DISCOVERY FALLBACK: %s - No matching device found", self.device_name)
            
        except Exception as e:
            _LOGGER.debug("🔍 DISCOVERY FALLBACK: %s - Exception: %s", self.device_name, e)

    async def _try_connect_at_ip(self, ip_address: str) -> bool:
        """Try to connect to device at specific IP address."""
        try:
            log_connection_test_start(self.device_name, ip_address)
            
            from ..discovery import async_discover_device_by_ip
            device = await async_discover_device_by_ip(ip_address, enhance_with_hardware=True)
            
            if device:
                log_connection_test_success(self.device_name, ip_address)
                return True
            else:
                log_connection_test_failed(self.device_name, ip_address, "No device found")
                return False
                
        except Exception as err:
            log_connection_test_failed(self.device_name, ip_address, str(err))
            return False

    async def recover_device_ip(self) -> Optional[str]:
        """Attempt to recover device IP using MAC address lookup."""
        if not self.mac_address:
            _LOGGER.debug("%s IP recovery BLOCKED: No MAC address available", self.device_name)
            return None

        _LOGGER.debug("%s IP recovery: Starting 3-method approach with MAC %s", self.device_name, self.mac_address)

        # Method 1: ARP table lookup
        _LOGGER.debug("%s IP recovery: METHOD 1 - ARP table lookup", self.device_name)
        new_ip = await self._get_ip_from_arp_table(self.mac_address)
        if new_ip:
            _LOGGER.debug("%s IP recovery: METHOD 1 SUCCESS - Found IP %s in ARP table", self.device_name, new_ip)
            return new_ip
        else:
            _LOGGER.debug("%s IP recovery: METHOD 1 FAILED - No IP found in ARP table", self.device_name)

        # Method 2: Ping subnet + ARP retry
        _LOGGER.debug("%s IP recovery: METHOD 2 - Ping subnet then retry ARP", self.device_name)
        await self._ping_subnet_to_populate_arp()
        new_ip = await self._get_ip_from_arp_table(self.mac_address)
        if new_ip:
            _LOGGER.debug("%s IP recovery: METHOD 2 SUCCESS - Found IP %s after subnet ping", self.device_name, new_ip)
            return new_ip
        else:
            _LOGGER.debug("%s IP recovery: METHOD 2 FAILED - No IP found after subnet ping", self.device_name)

        # Method 3: Discovery fallback
        _LOGGER.debug("%s IP recovery: METHOD 3 - Discovery fallback", self.device_name)
        new_ip = await self._find_device_via_discovery()
        if new_ip:
            _LOGGER.debug("%s IP recovery: METHOD 3 SUCCESS - Found IP %s via discovery", self.device_name, new_ip)
            return new_ip
        else:
            _LOGGER.debug("%s IP recovery: METHOD 3 FAILED - No IP found via discovery", self.device_name)

        _LOGGER.debug("%s IP recovery: ALL METHODS FAILED", self.device_name)
        return None

    async def _get_ip_from_arp_table(self, mac_address: str) -> Optional[str]:
        """Get IP address from system ARP table by MAC address."""
        try:
            system = platform.system().lower()
            if system == "windows":
                cmd = ["arp", "-a"]
            else:
                cmd = ["arp", "-a"]

            _LOGGER.debug("%s ARP lookup: Running command %s on %s", self.device_name, cmd, system)

            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                _LOGGER.debug("%s ARP lookup: Command failed with return code %d", self.device_name, result.returncode)
                if stderr:
                    _LOGGER.debug("%s ARP lookup: Error output: %s", self.device_name, stderr.decode().strip())
                return None

            arp_output = stdout.decode()
            _LOGGER.debug("%s ARP lookup: Got %d lines of output", self.device_name, len(arp_output.split('\n')))

            # Normalize MAC for search (both formats)
            mac_clean = mac_address.lower().replace(':', '-')
            mac_colon = mac_address.lower().replace('-', ':')
            _LOGGER.debug("%s ARP lookup: Searching for MAC formats: %s or %s", self.device_name, mac_clean, mac_colon)

            matches_found = 0
            for line in arp_output.split('\n'):
                line_lower = line.lower()
                if mac_clean in line_lower or mac_colon in line_lower:
                    matches_found += 1
                    _LOGGER.debug("%s ARP lookup: Found MAC match in line: %s", self.device_name, line.strip())
                    ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                    if ip_match:
                        found_ip = ip_match.group(1)
                        _LOGGER.debug("%s ARP lookup: Extracted IP %s from line", self.device_name, found_ip)
                        if found_ip != self.device_ip:
                            _LOGGER.debug("%s ARP lookup: Found NEW IP %s (current: %s)",
                                       self.device_name, found_ip, self.device_ip)
                            return found_ip
                        else:
                            _LOGGER.debug("%s ARP lookup: Found SAME IP %s, continuing search", self.device_name, found_ip)

            if matches_found == 0:
                _LOGGER.debug("%s ARP lookup: No MAC matches found in ARP table", self.device_name)
            else:
                _LOGGER.debug("%s ARP lookup: Found %d MAC matches but no new IP", self.device_name, matches_found)

            return None

        except Exception as e:
            _LOGGER.debug("%s ARP lookup: Exception occurred: %s", self.device_name, e)
            return None

    async def _ping_subnet_to_populate_arp(self) -> None:
        """Ping subnet to populate ARP table."""
        try:
            # Extract subnet from current IP
            ip_parts = self.device_ip.split('.')
            if len(ip_parts) != 4:
                _LOGGER.debug("%s Subnet ping: Invalid IP format: %s", self.device_name, self.device_ip)
                return

            subnet_base = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}"
            _LOGGER.debug("%s Subnet ping: Pinging subnet %s.x to populate ARP", self.device_name, subnet_base)

            # Ping common IPs in subnet (1, 10, 20, 50, 100, 200, 254)
            ping_targets = [1, 10, 20, 50, 100, 200, 254]
            ping_tasks = []

            for host in ping_targets:
                target_ip = f"{subnet_base}.{host}"
                if target_ip != self.device_ip:  # Don't ping current IP
                    ping_tasks.append(self._ping_single_ip(target_ip))

            # Run pings concurrently with timeout
            try:
                await asyncio.wait_for(asyncio.gather(*ping_tasks, return_exceptions=True), timeout=10)
                _LOGGER.debug("%s Subnet ping: Completed pinging %d targets", self.device_name, len(ping_targets))
            except asyncio.TimeoutError:
                _LOGGER.debug("%s Subnet ping: Timeout after 10 seconds", self.device_name)

        except Exception as e:
            _LOGGER.debug("%s Subnet ping: Exception: %s", self.device_name, e)

    async def _ping_single_ip(self, ip: str) -> None:
        """Ping a single IP address to populate ARP table."""
        try:
            system = platform.system().lower()
            if system == "windows":
                cmd = ["ping", "-n", "1", "-w", "1000", ip]
            else:
                cmd = ["ping", "-c", "1", "-W", "1", ip]

            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await result.communicate()

        except Exception:
            pass  # Ignore ping failures - we just want to populate ARP

    async def _find_device_via_discovery(self) -> Optional[str]:
        """Find device via discovery using MAC matching."""
        try:
            from ..discovery import async_discover_devices

            _LOGGER.debug("%s Discovery: Starting network discovery", self.device_name)
            devices = await async_discover_devices(enhance_with_hardware=True)

            if not devices:
                _LOGGER.debug("%s Discovery: No devices found on network", self.device_name)
                return None

            _LOGGER.debug("%s Discovery: Found %d devices, searching for MAC match", self.device_name, len(devices))

            # Normalize target MAC for comparison
            target_mac = self._normalize_mac(self.mac_address)

            for i, device in enumerate(devices):
                device_mac = device.get("mac") or device.get("pclmac", "")
                device_ip = device.get("ip", "")

                if device_mac:
                    normalized_device_mac = self._normalize_mac(device_mac)
                    _LOGGER.debug("%s Discovery: Device %d - IP: %s, MAC: %s (normalized: %s)",
                                 self.device_name, i+1, device_ip, device_mac, normalized_device_mac)

                    if normalized_device_mac == target_mac:
                        if device_ip and device_ip != self.device_ip:
                            _LOGGER.debug("%s Discovery: MATCH FOUND - IP: %s, MAC: %s",
                                         self.device_name, device_ip, device_mac)
                            return device_ip
                        else:
                            _LOGGER.debug("%s Discovery: MAC match but same IP: %s", self.device_name, device_ip)

            _LOGGER.debug("%s Discovery: No matching device found", self.device_name)
            return None

        except Exception as e:
            _LOGGER.debug("%s Discovery: Exception: %s", self.device_name, e)
            return None

    async def recover_missing_mac_address(self) -> None:
        """Auto-migration: Recover missing MAC address via direct IP discovery."""
        if self.mac_address:
            return  # MAC already available

        _LOGGER.warning("🔧 MAC RECOVERY: %s - No MAC address found, attempting recovery", self.device_name)

        try:
            await asyncio.sleep(2)  # Brief wait

            _LOGGER.debug("🔧 MAC RECOVERY: Starting DIRECT discovery at IP %s", self.device_ip)

            from ..discovery import async_discover_device_by_ip
            device = await async_discover_device_by_ip(self.device_ip, enhance_with_hardware=True)

            if device:
                _LOGGER.debug("🔧 MAC RECOVERY: DIRECT discovery result = %s", device)

                device_mac = device.get("mac", "")
                device_cpu_id = device.get("cpuid", "")

                _LOGGER.debug("🔧 MAC RECOVERY: Extracted - MAC: '%s', CPU: '%s'", device_mac, device_cpu_id)

                if device_mac:
                    _LOGGER.warning("🔧 MAC RECOVERY: FOUND MAC %s at IP %s", device_mac, self.device_ip)

                    # Update coordinator
                    self.mac_address = device_mac
                    self.coordinator.mac_address = device_mac
                    self.coordinator.ip_recovery.mac_address = device_mac

                    # Update config entry with new key format
                    new_data = dict(self.config_entry.data)
                    new_data["mac"] = device_mac  # Use new key format

                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data=new_data
                    )

                    _LOGGER.debug("✅ MAC RECOVERY: Successfully updated MAC address to %s", device_mac)
                    return
                else:
                    _LOGGER.warning("❌ MAC RECOVERY: Device found but MAC is empty!")
            else:
                _LOGGER.warning("❌ MAC RECOVERY: No device found at IP %s", self.device_ip)

        except Exception as e:
            _LOGGER.error("💥 MAC RECOVERY: Failed to recover MAC address: %s", e, exc_info=True)

    def _normalize_mac(self, mac: str) -> str:
        """Normalize MAC address for comparison."""
        return mac.lower().replace(':', '').replace('-', '')

    async def _change_device_ip(self, new_ip: str, source: str = "unknown") -> bool:
        """
        Change device IP and restart connection - common method for ARP recovery and user options.

        Args:
            new_ip: New IP address
            source: Source of change ("arp_recovery" or "user_options")

        Returns:
            True if successful, False otherwise
        """
        try:
            log_config_raw_before(source, dict(self.config_entry.data))

            # Update config entry
            await self._update_device_ip(new_ip)

            # For automatic recovery (ARP/discovery), don't reload - just update in place
            if source in ["arp_recovery", "discovery_recovery"]:
                # Stop current device
                if self.coordinator.device:
                    try:
                        await self.coordinator.device.stop_adaptive_polling()
                        await self.coordinator.device.close()
                    except Exception as err:
                        _LOGGER.debug("Error stopping device during IP change: %s", err)

                # Create new device with new IP
                self.coordinator.device = MaxSmartDevice(new_ip)
                await self.coordinator.device.initialize_device()

                # Reset state for fresh start
                self.coordinator._initialized = False
                self.coordinator.error_tracker.consecutive_errors = 0
                self.coordinator.ip_recovery.reset_on_success()

                _LOGGER.info("✅ IP CHANGE: %s - Successfully changed IP to %s",
                             self.device_name, new_ip)
                return True
            else:
                # For user-initiated changes, do full reload
                # Stop current device
                if self.coordinator.device:
                    try:
                        await self.coordinator.device.stop_adaptive_polling()
                        await self.coordinator.device.close()
                    except Exception as err:
                        _LOGGER.debug("Error stopping device during IP change: %s", err)

                # Reset state
                self.coordinator.device = None
                self.coordinator._initialized = False

                # Cancel error detection task
                if self.coordinator._error_detection_task:
                    self.coordinator._error_detection_task.cancel()

                # Reset trackers for fresh start
                from .error_tracking import SmartErrorTracker
                self.coordinator.error_tracker = SmartErrorTracker(self.device_name)
                self.coordinator.ip_recovery = ConservativeIPRecovery(self.device_name, self.mac_address)

                # Reload config entry to ensure HA knows about the change
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)

                _LOGGER.info("✅ IP CHANGE: %s - Successfully changed IP to %s",
                             self.device_name, new_ip)
                return True

        except Exception as e:
            _LOGGER.error("❌ IP CHANGE: %s - Failed to change IP to %s (%s): %s",
                         self.device_name, new_ip, source, e)
            return False

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
            self.coordinator.device_ip = new_ip
            log_config_raw_after(new_data)

        except Exception as e:
            _LOGGER.error("Failed to update device IP for %s: %s", self.device_name, e)
