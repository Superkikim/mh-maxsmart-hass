# custom_components/maxsmart/coordinator.py
"""MaxSmart coordinator with intelligent polling and conservative IP recovery."""

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
                _LOGGER.warning("Network cascade detected: %d MaxSmart devices offline (possible network issue)", 
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

class ConservativeIPRecovery:
    """Conservative IP recovery with escalating timeline: 10min, 30min, 60min, abandon."""
    
    def __init__(self, device_name: str, mac_address: str):
        """Initialize conservative IP recovery with escalating timeline."""
        self.device_name = device_name
        self.mac_address = mac_address
        
        # Escalating timeline: after 3 retries fail, then 10min, 30min, 60min, abandon
        self.max_attempts = 4  # 4 IP recovery attempts total
        self.escalation_timeline = [0, 600, 1800, 3600]  # 0, 10min, 30min, 60min in seconds
        
        # State tracking
        self.attempts_made = 0
        self.last_attempt_time = 0
        self.exhausted = False
        self.device_offline_start = None  # Track when device went offline
        
    def set_device_offline_start(self, offline_time: float) -> None:
        """Set when the device first went offline (for timeline calculation)."""
        if self.device_offline_start is None:
            self.device_offline_start = offline_time
            
    def can_attempt_recovery(self, current_time: float) -> bool:
        """Check if IP recovery can be attempted based on escalating timeline."""
        _LOGGER.debug("%s IP recovery check: MAC=%s, exhausted=%s, attempts=%d/%d",
                     self.device_name, self.mac_address[:8] + "..." if self.mac_address else "None",
                     self.exhausted, self.attempts_made, self.max_attempts)

        if not self.mac_address:
            _LOGGER.debug("%s IP recovery blocked: No MAC address available", self.device_name)
            return False

        if self.exhausted:
            _LOGGER.debug("%s IP recovery blocked: Recovery exhausted", self.device_name)
            return False

        if self.attempts_made >= self.max_attempts:
            self.exhausted = True
            _LOGGER.info("%s IP recovery exhausted (%d/%d attempts), device requires manual intervention",
                        self.device_name, self.attempts_made, self.max_attempts)
            return False

        # Check if device has been offline long enough for next attempt
        if self.device_offline_start is None:
            _LOGGER.debug("%s IP recovery blocked: No offline start time set", self.device_name)
            return False

        time_offline = current_time - self.device_offline_start
        required_offline_time = self.escalation_timeline[self.attempts_made]

        _LOGGER.debug("%s IP recovery timing: offline=%.0fs, required=%.0fs, next_attempt=%d",
                     self.device_name, time_offline, required_offline_time, self.attempts_made)

        if time_offline < required_offline_time:
            remaining = required_offline_time - time_offline
            _LOGGER.debug("%s IP recovery blocked: Need %.0fs more offline time", self.device_name, remaining)
            return False

        # Ensure minimum cooldown between attempts (30 seconds)
        if (current_time - self.last_attempt_time) < 30:
            cooldown_remaining = 30 - (current_time - self.last_attempt_time)
            _LOGGER.debug("%s IP recovery blocked: Cooldown remaining %.0fs", self.device_name, cooldown_remaining)
            return False

        _LOGGER.debug("%s IP recovery ALLOWED: All conditions met", self.device_name)
        return True
    
    def start_attempt(self, current_time: float) -> None:
        """Record the start of an IP recovery attempt."""
        self.attempts_made += 1
        self.last_attempt_time = current_time
        
        timeline_name = ["immediate", "10min", "30min", "60min"][self.attempts_made - 1]
        _LOGGER.info("%s starting IP recovery attempt %d/%d (%s mark)", 
                    self.device_name, self.attempts_made, self.max_attempts, timeline_name)
    
    def reset_on_success(self) -> None:
        """Reset attempts counter on successful connection."""
        if self.attempts_made > 0:
            _LOGGER.info("%s IP recovery successful, resetting attempt counter", self.device_name)
            self.attempts_made = 0
            self.exhausted = False
            self.device_offline_start = None
    
    def get_status(self) -> Dict[str, Any]:
        """Get recovery status for diagnostics."""
        current_time = time.time()
        next_attempt_time = None
        
        if not self.exhausted and self.attempts_made < self.max_attempts and self.device_offline_start:
            next_required_offline = self.escalation_timeline[self.attempts_made]
            next_attempt_time = self.device_offline_start + next_required_offline
        
        return {
            "attempts_made": self.attempts_made,
            "max_attempts": self.max_attempts,
            "exhausted": self.exhausted,
            "device_offline_start": self.device_offline_start,
            "time_offline": current_time - self.device_offline_start if self.device_offline_start else None,
            "next_attempt_in": max(0, next_attempt_time - current_time) if next_attempt_time else None,
            "can_attempt": self.can_attempt_recovery(current_time),
        }
    
class SmartErrorTracker:
    """Smart error tracking to prevent log pollution."""
    
    def __init__(self, device_name: str):
        """Initialize smart error tracker."""
        self.device_name = device_name
        
        # Error state tracking
        self.consecutive_errors = 0
        self.total_errors = 0
        self.last_error_type = None
        self.first_error_time = None
        self.last_successful_poll = time.time()
        
        # Smart logging
        self.last_warning_time = 0
        self.warning_interval = 300  # 5 minutes between warnings
        self.error_silence_after = 900  # Stop logging after 15 minutes of errors
        
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
            
        # Stop logging after prolonged errors
        if self.first_error_time and (current_time - self.first_error_time) > self.error_silence_after:
            return False
            
        # Log every 5 minutes for connection errors
        if (current_time - self.last_warning_time) >= self.warning_interval:
            self.last_warning_time = current_time
            return True
            
        return False
    
    def is_device_considered_offline(self) -> bool:
        """Check if device should be considered offline."""
        current_time = time.time()
        time_since_last_poll = current_time - self.last_successful_poll
        
        # Consider offline after 120 seconds without successful poll
        return time_since_last_poll > 120 and self.last_successful_poll > 0
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get status summary for diagnostics."""
        current_time = time.time()
        return {
            "consecutive_errors": self.consecutive_errors,
            "total_errors": self.total_errors,
            "last_error_type": self.last_error_type,
            "time_since_last_success": current_time - self.last_successful_poll if self.last_successful_poll > 0 else None,
            "considered_offline": self.is_device_considered_offline(),
        }

class MaxSmartCoordinator(DataUpdateCoordinator):
    """Enhanced coordinator with intelligent polling and conservative IP recovery."""

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

        # Debug: Log what we extracted
        _LOGGER.debug("🔍 COORDINATOR INIT: Extracted MAC='%s', CPU_ID='%s', Method='%s'",
                       self.mac_address, self.cpu_id, self.identification_method)

        # Auto-migration: If MAC address is missing, try to recover it
        if not self.mac_address and self.cpu_id:
            _LOGGER.debug("🔧 AUTO-MIGRATION: MAC address missing, attempting recovery via discovery")
            asyncio.create_task(self._recover_missing_mac_address())
        
        self.device: Optional[MaxSmartDevice] = None
        self._initialized = False
        
        # Conservative IP recovery
        self.ip_recovery = ConservativeIPRecovery(self.device_name, self.mac_address)
        
        # Smart error tracking
        self.error_tracker = SmartErrorTracker(self.device_name)
        
        # Polling statistics
        self._successful_polls = 0
        
        # Error detection task
        self._error_detection_task = None

    async def async_config_entry_first_refresh(self) -> None:
        """Override first refresh to perform our custom setup."""
        _LOGGER.info("🚀 COORDINATOR: Starting first refresh for %s", self.device_name)
        await self._async_setup()

        # Call parent's first refresh only if we're initialized
        if self._initialized:
            _LOGGER.info("🚀 COORDINATOR: Device initialized, calling parent first refresh")
            await super().async_config_entry_first_refresh()
        else:
            _LOGGER.warning("🚀 COORDINATOR: Device not initialized, skipping parent first refresh")
            # Set empty data for offline devices
            self.async_set_updated_data({})

    async def _async_setup(self) -> None:
        """Set up the coordinator - simplified without startup IP recovery."""
        if self._initialized:
            return

        try:
            _LOGGER.info("🔄 MAXSMART SETUP: Starting initialization for %s at IP %s", self.device_name, self.device_ip)

            # Log complete config entry data
            _LOGGER.warning("📋 CONFIG ENTRY DATA: Complete entry data = %s", dict(self.config_entry.data))
            _LOGGER.warning("📋 CONFIG ENTRY OPTIONS: Complete entry options = %s", dict(self.config_entry.options))

            _LOGGER.info("🔄 MAXSMART SETUP: Device config - MAC: %s, CPU ID: %s, Method: %s",
                        self.mac_address or "None", self.cpu_id or "None", self.identification_method)

            # Try initial connection at stored IP
            _LOGGER.info("🔄 MAXSMART SETUP: Testing initial connection to %s", self.device_ip)
            success = await self._try_connect_at_ip(self.device_ip)

            if success:
                _LOGGER.info("✅ MAXSMART SETUP: Initial connection SUCCESS, completing setup")
                await self._complete_successful_setup()
                return

            # Initial connection failed - device is offline, set up resilient mode
            _LOGGER.warning("❌ MAXSMART SETUP: Initial connection FAILED, creating resilient setup for %s", self.device_name)
            self._create_resilient_setup()

        except Exception as err:
            should_log = self.error_tracker.record_error("setup_error")
            if should_log:
                _LOGGER.error("💥 MAXSMART SETUP: Unexpected error initializing %s: %s", self.device_name, err, exc_info=True)
            raise UpdateFailed(f"Setup failed for {self.device_name}: {err}")

    async def _try_connect_at_ip(self, ip_address: str) -> bool:
        """Try to connect to device at specific IP address."""
        try:
            _LOGGER.info("🔌 CONNECTION TEST: %s - Creating device instance for IP %s", self.device_name, ip_address)
            temp_device = MaxSmartDevice(ip_address)

            _LOGGER.info("🔌 CONNECTION TEST: %s - Calling initialize_device() for %s", self.device_name, ip_address)
            await temp_device.initialize_device()

            _LOGGER.info("🔌 CONNECTION TEST: %s - Closing test connection to %s", self.device_name, ip_address)
            await temp_device.close()

            _LOGGER.info("✅ CONNECTION TEST: %s - SUCCESS at %s", self.device_name, ip_address)
            return True

        except Exception as err:
            _LOGGER.warning("❌ CONNECTION TEST: %s - FAILED at %s: %s - %s", self.device_name, ip_address, type(err).__name__, err)
            return False

    async def _attempt_startup_ip_recovery(self) -> Optional[str]:
        """Attempt IP recovery at startup - limited to one attempt."""
        if not self.ip_recovery.can_attempt_recovery():
            return None
            
        self.ip_recovery.start_attempt()
        
        try:
            new_ip = await self._recover_device_ip()
            if new_ip and new_ip != self.device_ip:
                _LOGGER.info("%s startup IP recovery found new address: %s -> %s", 
                           self.device_name, self.device_ip, new_ip)
                return new_ip
            else:
                _LOGGER.debug("%s startup IP recovery found no new address", self.device_name)
                return None
                
        except Exception as err:
            _LOGGER.debug("%s startup IP recovery failed: %s", self.device_name, err)
            return None

    async def _complete_successful_setup(self) -> None:
        """Complete successful device setup."""
        self.device = MaxSmartDevice(self.device_ip)
        await self.device.initialize_device()
        
        # Start intelligent polling with burst mode
        await self.device.start_adaptive_polling(enable_burst=True)
        
        # Register single polling callback for real-time data updates
        self.device.register_poll_callback("coordinator", self._on_poll_data)
        
        # Start conservative error detection
        self._start_conservative_error_detection()
        
        # Reset IP recovery on successful connection
        self.ip_recovery.reset_on_success()
        
        self._initialized = True
        
        # Log successful initialization
        hw_info = self._format_hardware_info()
        _LOGGER.info("MaxSmart device ready: %s (%s)%s", 
                    self.device_name, self.device_ip, hw_info)

    def _create_resilient_setup(self) -> None:
        """Create resilient setup for offline devices."""
        _LOGGER.warning("🔄 RESILIENT SETUP: %s - Device offline, starting resilient mode", self.device_name)
        self._initialized = False

        # Record setup failure
        self.error_tracker.record_error("setup_failed")

        # Start offline retry with conservative IP recovery
        _LOGGER.info("🔄 RESILIENT SETUP: %s - Starting offline retry loop", self.device_name)
        self._start_offline_retry()

    async def _on_poll_data(self, poll_data: Dict[str, Any]) -> None:
        """Callback for successful polling data from maxsmart intelligent polling."""
        try:
            device_data = poll_data.get("device_data", {})
            poll_count = poll_data.get("poll_count", 0)
            mode = poll_data.get("mode", "unknown")
            
            # Track successful poll
            self._successful_polls += 1
            self.error_tracker.record_successful_poll()
            
            # Reset IP recovery on successful polls
            self.ip_recovery.reset_on_success()
            
            # Periodic success logging (conservative)
            if self._successful_polls % 300 == 0:  # Every 300 polls instead of 200
                _LOGGER.debug("MaxSmart polling: %s - %d successful polls, %d errors (mode: %s)", 
                            self.device_name, self._successful_polls, self.error_tracker.total_errors, mode)
            
            # Update HA coordinator data - This triggers entity updates
            self.async_set_updated_data(device_data)
            
        except Exception as err:
            _LOGGER.error("Error processing poll data for %s: %s", self.device_name, err)

    def _start_offline_retry(self) -> None:
        """Start periodic retry for offline devices."""
        _LOGGER.info("🔄 START OFFLINE RETRY: %s - Creating retry task", self.device_name)
        if self._error_detection_task:
            self._error_detection_task.cancel()

        self._error_detection_task = asyncio.create_task(self._offline_retry_loop())
        _LOGGER.info("🔄 START OFFLINE RETRY: %s - Task created successfully", self.device_name)

    async def _offline_retry_loop(self) -> None:
        """Conservative retry loop for offline devices with integrated IP recovery."""
        _LOGGER.warning("🔄 OFFLINE RETRY LOOP: %s - ENTERING retry loop function", self.device_name)
        try:
            retry_interval = 60  # Start with 1 minute
            max_interval = 300   # Max 5 minutes
            offline_start_time = time.time()

            _LOGGER.warning("🔄 OFFLINE RETRY: %s - Starting retry loop (interval=%ds, max=%ds)",
                           self.device_name, retry_interval, max_interval)

            # Set offline start time for IP recovery timeline
            self.ip_recovery.set_device_offline_start(offline_start_time)
            _LOGGER.info("🔄 OFFLINE RETRY: %s - Set offline start time for IP recovery", self.device_name)

            _LOGGER.warning("🔄 OFFLINE RETRY LOOP: %s - About to enter while loop, initialized=%s",
                           self.device_name, self._initialized)

            while not self._initialized:
                _LOGGER.warning("🔄 OFFLINE RETRY LOOP: %s - Starting iteration, waiting %ds", self.device_name, retry_interval)
                await asyncio.sleep(retry_interval)
                current_time = time.time()

                _LOGGER.warning("🔄 OFFLINE RETRY LOOP: %s - Sleep completed, starting attempt", self.device_name)

                try:
                    _LOGGER.info("🔄 OFFLINE RETRY: %s - Attempt #%d (interval=%.1fs, errors=%d)",
                                 self.device_name, self.error_tracker.consecutive_errors + 1,
                                 retry_interval, self.error_tracker.consecutive_errors)

                    # Try original IP first
                    _LOGGER.info("🔄 OFFLINE RETRY: %s - Testing connection to original IP %s", self.device_name, self.device_ip)
                    success = await self._try_connect_at_ip(self.device_ip)

                    if success:
                        _LOGGER.info("✅ OFFLINE RETRY: %s - Original IP connection SUCCESS, completing setup", self.device_name)
                        await self._complete_successful_setup()
                        return
                    else:
                        _LOGGER.warning("❌ OFFLINE RETRY: %s - Original IP connection FAILED", self.device_name)

                    # Original IP failed - record error for smart logging
                    _LOGGER.warning("📊 ERROR TRACKING: %s - Recording connection_refused error", self.device_name)
                    should_log = self.error_tracker.record_error("connection_refused")
                    _LOGGER.warning("📊 ERROR TRACKING: %s - Error recorded, consecutive_errors=%d",
                                   self.device_name, self.error_tracker.consecutive_errors)

                    # 🚀 IMMEDIATE ARP CHECK: Check for IP change on every failure
                    if self.mac_address:
                        asyncio.create_task(self._immediate_arp_check())

                    # NEW: Check if IP recovery should be attempted based on consecutive failures
                    _LOGGER.warning("🔍 IP RECOVERY CHECK: %s - Errors=%d, threshold=3, MAC=%s",
                                 self.device_name, self.error_tracker.consecutive_errors,
                                 self.mac_address[:8] + "..." if self.mac_address else "None")

                    if self.error_tracker.consecutive_errors >= 3:
                        _LOGGER.info("✅ IP RECOVERY CHECK: %s - Error threshold met (%d >= 3)",
                                     self.device_name, self.error_tracker.consecutive_errors)

                        can_recover = self.ip_recovery.can_attempt_recovery(current_time)
                        _LOGGER.info("🔍 IP RECOVERY CHECK: %s - Can attempt recovery: %s", self.device_name, can_recover)

                        if can_recover:
                            _LOGGER.warning("🚀 IP RECOVERY: %s - TRIGGERING IP recovery (errors >= 3)", self.device_name)
                            new_ip = await self._attempt_runtime_ip_recovery(current_time)
                            if new_ip:
                                _LOGGER.info("🔍 IP RECOVERY: %s - Testing connection to recovered IP %s", self.device_name, new_ip)
                                success = await self._try_connect_at_ip(new_ip)
                                if success:
                                    _LOGGER.info("✅ IP RECOVERY: %s - Recovered IP connection SUCCESS, updating config", self.device_name)
                                    await self._update_device_ip(new_ip)
                                    await self._complete_successful_setup()
                                    return
                                else:
                                    _LOGGER.warning("❌ IP RECOVERY: %s - Recovered IP connection FAILED", self.device_name)
                            else:
                                _LOGGER.warning("❌ IP RECOVERY: %s - No new IP found", self.device_name)
                        else:
                            recovery_status = self.ip_recovery.get_status()
                            _LOGGER.info("⏳ IP RECOVERY: %s - Not ready yet - %s", self.device_name, recovery_status)
                    else:
                        _LOGGER.info("⏳ IP RECOVERY CHECK: %s - Need %d more errors (current: %d)",
                                     self.device_name, 3 - self.error_tracker.consecutive_errors,
                                     self.error_tracker.consecutive_errors)

                    # Both failed - increase retry interval (normal retry logic continues)
                    old_interval = retry_interval
                    retry_interval = min(retry_interval * 1.5, max_interval)
                    _LOGGER.debug("%s Offline retry: Increasing retry interval %.1fs -> %.1fs",
                                 self.device_name, old_interval, retry_interval)

                except Exception as e:
                    _LOGGER.error("💥 OFFLINE RETRY EXCEPTION: %s - Exception during retry: %s", self.device_name, e, exc_info=True)
                    retry_interval = min(retry_interval * 1.5, max_interval)
                    continue
                    
        except asyncio.CancelledError:
            pass
        except Exception as err:
            _LOGGER.error("Offline retry loop failed for %s: %s", self.device_name, err)
    def _start_conservative_error_detection(self) -> None:
        """Start background task with conservative error detection."""
        if self._error_detection_task:
            self._error_detection_task.cancel()
            
        self._error_detection_task = asyncio.create_task(self._conservative_error_detection_loop())

    async def _conservative_error_detection_loop(self) -> None:
        """Conservative error detection loop with integrated IP recovery timeline."""
        try:
            _LOGGER.debug("%s Error detection: Starting conservative error detection loop", self.device_name)
            while self._initialized:
                await asyncio.sleep(120)  # Check every 2 minutes
                current_time = time.time()

                # Get current status for debugging
                is_offline = self.error_tracker.is_device_considered_offline()
                consecutive_errors = self.error_tracker.consecutive_errors
                time_since_last_poll = current_time - self.error_tracker.last_successful_poll

                _LOGGER.debug("%s Error detection: Check - offline=%s, errors=%d, time_since_poll=%.0fs",
                             self.device_name, is_offline, consecutive_errors, time_since_last_poll)

                # Check if device is considered offline
                if is_offline:
                    _LOGGER.debug("%s Error detection: Device considered OFFLINE, processing...", self.device_name)

                    # Set offline start time for IP recovery timeline
                    if self.error_tracker.first_error_time:
                        self.ip_recovery.set_device_offline_start(self.error_tracker.first_error_time)
                        _LOGGER.debug("%s Error detection: Set offline start time to %s",
                                     self.device_name, self.error_tracker.first_error_time)

                    # Record error for smart logging
                    should_log = self.error_tracker.record_error("polling_timeout")

                    if should_log:
                        time_offline = current_time - self.error_tracker.last_successful_poll
                        _LOGGER.warning("%s has been offline for %.0f seconds",
                                      self.device_name, time_offline)

                    # Check if IP recovery attempt should be made
                    can_recover = self.ip_recovery.can_attempt_recovery(current_time)
                    _LOGGER.debug("%s Error detection: IP recovery check result: %s", self.device_name, can_recover)

                    if can_recover:
                        _LOGGER.info("%s Error detection: TRIGGERING IP recovery attempt", self.device_name)
                        await self._attempt_runtime_ip_recovery(current_time)
                    else:
                        recovery_status = self.ip_recovery.get_status()
                        _LOGGER.debug("%s Error detection: IP recovery not ready - %s", self.device_name, recovery_status)
                else:
                    _LOGGER.debug("%s Error detection: Device status OK", self.device_name)

        except asyncio.CancelledError:
            _LOGGER.debug("%s Error detection: Loop cancelled", self.device_name)
            pass
        except Exception as err:
            _LOGGER.error("Conservative error detection loop failed for %s: %s", self.device_name, err, exc_info=True)

    async def _attempt_runtime_ip_recovery(self, current_time: float) -> Optional[str]:
        """Attempt conservative IP recovery during runtime with final exhaustion handling."""
        _LOGGER.info("🔍 IP RECOVERY: %s - Starting recovery (Current IP: %s, MAC: %s)",
                     self.device_name, self.device_ip, self.mac_address[:12] + "...")
        _LOGGER.warning("📋 CONFIG ENTRY RAW BEFORE: %s", dict(self.config_entry.data))

        self.ip_recovery.start_attempt(current_time)

        try:
            _LOGGER.debug("%s IP recovery: Beginning device IP lookup process", self.device_name)
            new_ip = await self._recover_device_ip()

            if new_ip and new_ip != self.device_ip:
                _LOGGER.info("✅ IP RECOVERY: %s - Found new address %s → %s",
                           self.device_name, self.device_ip, new_ip)

                # Test connection to new IP before switching
                _LOGGER.debug("%s IP recovery: Testing connection to new IP %s", self.device_name, new_ip)
                connection_test = await self._try_connect_at_ip(new_ip)

                if connection_test:
                    _LOGGER.info("%s IP recovery: Connection test to %s PASSED, switching", self.device_name, new_ip)
                    await self._restart_polling_with_new_ip(new_ip)
                    return new_ip
                else:
                    _LOGGER.warning("%s IP recovery: Connection test to %s FAILED, not switching", self.device_name, new_ip)
                    return None
            else:
                if new_ip == self.device_ip:
                    _LOGGER.debug("%s IP recovery: Found same IP %s, no change needed", self.device_name, new_ip)
                else:
                    _LOGGER.debug("%s IP recovery: No new IP found", self.device_name)

                # Check if this was the final attempt
                if self.ip_recovery.attempts_made >= self.ip_recovery.max_attempts:
                    _LOGGER.warning("%s IP recovery EXHAUSTED %d/%d - device requires manual intervention",
                                  self.device_name, self.ip_recovery.attempts_made, self.ip_recovery.max_attempts)

                return None

        except Exception as err:
            _LOGGER.error("%s IP recovery attempt FAILED with exception: %s", self.device_name, err, exc_info=True)

            # Check if this was the final attempt
            if self.ip_recovery.attempts_made >= self.ip_recovery.max_attempts:
                _LOGGER.warning("%s IP recovery EXHAUSTED %d/%d after exception - device requires manual intervention",
                              self.device_name, self.ip_recovery.attempts_made, self.ip_recovery.max_attempts)

            return None
    async def _restart_polling_with_new_ip(self, new_ip: str) -> None:
        """Restart intelligent polling with new IP address."""
        try:
            # Stop current polling
            if self.device:
                await self.device.stop_adaptive_polling()
                await self.device.close()
            
            # Update IP and create new device instance
            await self._update_device_ip(new_ip)
            self.device = MaxSmartDevice(new_ip)
            await self.device.initialize_device()

            # Log device info to verify firmware version and watt multiplier
            _LOGGER.debug("🔧 DEVICE RECREATED: Firmware=%s, WattFormat=%s, Multiplier=%s",
                         getattr(self.device, 'version', 'Unknown'),
                         getattr(self.device, '_watt_format', 'Unknown'),
                         getattr(self.device, '_watt_multiplier', 1.0))
            
            # Restart polling
            await self.device.start_adaptive_polling(enable_burst=True)
            self.device.register_poll_callback("coordinator", self._on_poll_data)
            
            # Reset recovery state
            self.ip_recovery.reset_on_success()
            
            _LOGGER.info("%s IP recovery successful, polling restarted with new IP %s", 
                       self.device_name, new_ip)
                       
        except Exception as err:
            _LOGGER.error("%s failed to restart polling with new IP: %s", self.device_name, err)

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fallback update method for offline devices."""
        # For offline devices, return empty data to keep entities in unavailable state
        if not self._initialized:
            return {}
            
        try:
            # Record this as a fallback attempt
            should_log = self.error_tracker.record_error("fallback_polling")
            
            if should_log:
                _LOGGER.warning("%s using fallback polling", self.device_name)
            
            data = await self.device.get_data()
            
            # If fallback succeeds, record it
            self.error_tracker.record_successful_poll()
            self.ip_recovery.reset_on_success()
            return data
            
        except Exception as err:
            should_log = self.error_tracker.record_error("fallback_failed")
            
            if should_log and not self.error_tracker.in_cascade:
                _LOGGER.error("%s fallback polling failed: %s", self.device_name, err)
                
            # Return empty data instead of raising UpdateFailed
            return {}

    async def _immediate_arp_check(self) -> None:
        """Immediate ARP check on every connection failure - lightweight IP recovery."""
        try:
            _LOGGER.debug("🔍 IMMEDIATE ARP: %s - Checking for IP change", self.device_name)

            # Quick ARP lookup
            new_ip = await self._get_ip_from_arp_table(self.mac_address)

            if new_ip and new_ip != self.device_ip:
                _LOGGER.info("🚀 IMMEDIATE ARP: %s - IP changed %s → %s, fixing immediately!",
                           self.device_name, self.device_ip, new_ip)

                # Test connection to new IP
                connection_test = await self._try_connect_at_ip(new_ip)
                if connection_test:
                    _LOGGER.info("✅ IMMEDIATE ARP: %s - New IP works, switching immediately", self.device_name)
                    await self._restart_polling_with_new_ip(new_ip)
                else:
                    _LOGGER.warning("❌ IMMEDIATE ARP: %s - New IP %s doesn't work", self.device_name, new_ip)
            else:
                _LOGGER.debug("🔍 IMMEDIATE ARP: %s - No IP change detected, continuing normal retry", self.device_name)

        except Exception as e:
            _LOGGER.debug("🔍 IMMEDIATE ARP: %s - Exception: %s", self.device_name, e)

    async def _recover_device_ip(self) -> Optional[str]:
        """Attempt to recover device IP using MAC address lookup."""
        if not self.mac_address:
            _LOGGER.debug("%s IP recovery BLOCKED: No MAC address available", self.device_name)
            return None

        _LOGGER.info("%s IP recovery: Starting 3-method approach with MAC %s", self.device_name, self.mac_address)

        # Method 1: ARP table lookup
        _LOGGER.debug("%s IP recovery: METHOD 1 - ARP table lookup", self.device_name)
        new_ip = await self._get_ip_from_arp_table(self.mac_address)
        if new_ip:
            _LOGGER.info("%s IP recovery: METHOD 1 SUCCESS - Found IP %s in ARP table", self.device_name, new_ip)
            return new_ip
        else:
            _LOGGER.debug("%s IP recovery: METHOD 1 FAILED - No IP found in ARP table", self.device_name)

        # Method 2: Ping subnet + ARP retry
        _LOGGER.debug("%s IP recovery: METHOD 2 - Ping subnet then retry ARP", self.device_name)
        await self._ping_subnet_to_populate_arp()
        new_ip = await self._get_ip_from_arp_table(self.mac_address)
        if new_ip:
            _LOGGER.info("%s IP recovery: METHOD 2 SUCCESS - Found IP %s after subnet ping", self.device_name, new_ip)
            return new_ip
        else:
            _LOGGER.debug("%s IP recovery: METHOD 2 FAILED - No IP found after subnet ping", self.device_name)

        # Method 3: Discovery fallback
        _LOGGER.debug("%s IP recovery: METHOD 3 - Discovery fallback", self.device_name)
        new_ip = await self._find_device_via_discovery()
        if new_ip:
            _LOGGER.info("%s IP recovery: METHOD 3 SUCCESS - Found IP %s via discovery", self.device_name, new_ip)
            return new_ip
        else:
            _LOGGER.debug("%s IP recovery: METHOD 3 FAILED - No IP found via discovery", self.device_name)

        _LOGGER.warning("%s IP recovery: ALL METHODS FAILED - No new IP found", self.device_name)
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
                            _LOGGER.info("%s ARP lookup: Found NEW IP %s (current: %s)",
                                       self.device_name, found_ip, self.device_ip)
                            return found_ip
                        else:
                            _LOGGER.debug("%s ARP lookup: Found SAME IP %s, continuing search", self.device_name, found_ip)

            if matches_found == 0:
                _LOGGER.debug("%s ARP lookup: No MAC matches found in ARP table", self.device_name)
            else:
                _LOGGER.debug("%s ARP lookup: Found %d MAC matches but no new IPs", self.device_name, matches_found)

        except Exception as e:
            _LOGGER.warning("%s ARP lookup: Exception occurred: %s", self.device_name, e, exc_info=True)

        return None

    async def _ping_subnet_to_populate_arp(self) -> None:
        """Ping subnet to populate ARP table."""
        try:
            subnet_base = '.'.join(self.device_ip.split('.')[:-1])
            broadcast_ip = f"{subnet_base}.255"

            system = platform.system().lower()
            if system == "windows":
                cmd = ["ping", "-n", "1", "-w", "1000", broadcast_ip]
            else:
                cmd = ["ping", "-c", "1", "-W", "1", broadcast_ip]

            _LOGGER.debug("%s Subnet ping: Pinging %s with command %s on %s",
                         self.device_name, broadcast_ip, cmd, system)

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            _LOGGER.debug("%s Subnet ping: Command completed with return code %d",
                         self.device_name, process.returncode)

            if process.returncode == 0:
                _LOGGER.debug("%s Subnet ping: Broadcast ping successful", self.device_name)
            else:
                _LOGGER.debug("%s Subnet ping: Broadcast ping failed (this is often normal)", self.device_name)

            # Wait for ARP table to populate
            _LOGGER.debug("%s Subnet ping: Waiting 0.5s for ARP table population", self.device_name)
            await asyncio.sleep(0.5)

        except Exception as e:
            _LOGGER.warning("%s Subnet ping: Exception occurred: %s", self.device_name, e, exc_info=True)

    async def _find_device_via_discovery(self) -> Optional[str]:
        """Find device via discovery using MAC matching."""
        try:
            _LOGGER.debug("%s Discovery: Starting MaxSmart discovery with hardware enhancement", self.device_name)
            devices = await MaxSmartDiscovery.discover_maxsmart(enhance_with_hardware_ids=True)

            _LOGGER.debug("%s Discovery: Found %d devices", self.device_name, len(devices))

            # Log raw discovery data
            for i, device in enumerate(devices):
                _LOGGER.warning("🔍 DISCOVERY RAW DEVICE %d: %s", i+1, device)

            # Primary: MAC address matching
            target_mac_normalized = self._normalize_mac(self.mac_address)
            _LOGGER.debug("%s Discovery: Looking for MAC %s (normalized: %s)",
                         self.device_name, self.mac_address, target_mac_normalized)

            for i, device in enumerate(devices):
                device_mac = device.get("mac") or device.get("pclmac", "")  # Fixed: use "mac" key
                device_ip = device.get("ip", "unknown")

                _LOGGER.debug("%s Discovery: Device %d - IP: %s, MAC: %s",
                             self.device_name, i+1, device_ip, device_mac)

                if device_mac:
                    device_mac_normalized = self._normalize_mac(device_mac)
                    if device_mac_normalized == target_mac_normalized:
                        _LOGGER.info("%s Discovery: MAC MATCH found - IP %s, MAC %s",
                                   self.device_name, device_ip, device_mac)
                        return device_ip
                    else:
                        _LOGGER.debug("%s Discovery: MAC mismatch - got %s, want %s",
                                     self.device_name, device_mac_normalized, target_mac_normalized)

            # Fallback: CPU ID match
            if self.cpu_id:
                _LOGGER.debug("%s Discovery: No MAC match, trying CPU ID fallback: %s",
                             self.device_name, self.cpu_id)
                for i, device in enumerate(devices):
                    device_cpu_id = device.get("cpuid", "")
                    device_ip = device.get("ip", "unknown")

                    _LOGGER.debug("%s Discovery: Device %d CPU ID check - IP: %s, CPU ID: %s",
                                 self.device_name, i+1, device_ip, device_cpu_id)

                    if device_cpu_id == self.cpu_id:
                        _LOGGER.info("%s Discovery: CPU ID MATCH found - IP %s, CPU ID %s",
                                   self.device_name, device_ip, device_cpu_id)
                        return device_ip
            else:
                _LOGGER.debug("%s Discovery: No CPU ID available for fallback", self.device_name)

            _LOGGER.debug("%s Discovery: No matching device found", self.device_name)

        except Exception as e:
            _LOGGER.warning("%s Discovery: Exception occurred: %s", self.device_name, e, exc_info=True)

        return None

    async def _recover_missing_mac_address(self) -> None:
        """Auto-migration: Recover missing MAC address via direct IP discovery."""
        try:
            await asyncio.sleep(2)  # Brief wait

            _LOGGER.debug("🔧 MAC RECOVERY: Starting DIRECT discovery at IP %s", self.device_ip)

            from .discovery import async_discover_device_by_ip
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
                    self.ip_recovery.mac_address = device_mac

                    # Update config entry
                    new_data = dict(self.config_entry.data)
                    new_data["mac_address"] = device_mac

                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data=new_data
                    )

                    _LOGGER.info("✅ MAC RECOVERY: Successfully updated MAC address to %s", device_mac)
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
            _LOGGER.warning("📋 CONFIG ENTRY RAW AFTER: %s", new_data)
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
            
            await self.device.turn_on(port_id)
            _LOGGER.debug("Port %d turned on successfully for %s", port_id, self.device_name)
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
            
            await self.device.turn_off(port_id)
            _LOGGER.debug("Port %d turned off successfully for %s", port_id, self.device_name)
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
                
                # Conservative IP recovery status
                "ip_recovery": self.ip_recovery.get_status(),
                
                # Smart polling statistics
                "polling_system": "maxsmart_intelligent",
                "polling_active": self.device.is_polling if self.device else False,
                "successful_polls": self._successful_polls,
                
                # Smart error tracking
                "error_tracker": self.error_tracker.get_status_summary(),
                
                # Support capabilities
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
        
        old_ip = self.device_ip
        old_device_name = self.device_name
        
        # Update coordinator properties from new config
        self.device_name = self.config_entry.data["device_name"]
        self.name = f"MaxSmart {self.device_name}"
        
        new_ip = self.config_entry.data["device_ip"]
        
        # Check what changed
        ip_changed = new_ip != old_ip
        device_name_changed = self.device_name != old_device_name
        
        if ip_changed:
            _LOGGER.info("📋 CONFIG ENTRY AFTER: device_ip=%s → %s", old_ip, new_ip)
            await self._handle_manual_ip_change(new_ip)
        elif device_name_changed:
            _LOGGER.info("Device name updated: %s → %s", old_device_name, self.device_name)
            # Just name changes, no reconnection needed
        else:
            # Only port names changed, coordinator doesn't need to reconnect
            _LOGGER.debug("Port names updated for %s, no coordinator changes needed", self.device_name)

    async def _handle_manual_ip_change(self, new_ip: str) -> None:
        """Handle manual IP address change from options flow."""
        self.device_ip = new_ip
        
        # Cancel error detection task
        if self._error_detection_task:
            self._error_detection_task.cancel()
            
        # Stop current device connection
        if self.device:
            try:
                await self.device.stop_adaptive_polling()
                await self.device.close()
            except Exception as err:
                _LOGGER.debug("Error stopping device during IP change: %s", err)
                
        self.device = None
        self._initialized = False
        
        # Reset trackers for fresh start with new IP
        self.error_tracker = SmartErrorTracker(self.device_name)
        # Keep IP recovery state - user manually changed IP so reset attempts
        self.ip_recovery = ConservativeIPRecovery(self.device_name, self.mac_address)
        
        # Immediately try to connect to new IP
        try:
            _LOGGER.info("Attempting immediate connection to new IP: %s", new_ip)
            await self._complete_successful_setup()
            _LOGGER.info("Successfully connected to %s at new IP %s", self.device_name, new_ip)
            
        except Exception as err:
            _LOGGER.warning("Failed to connect to new IP %s for %s: %s", new_ip, self.device_name, err)
            # Create resilient setup for the new IP
            self._create_resilient_setup()

    async def async_shutdown(self) -> None:
        """Shutdown coordinator with intelligent polling cleanup."""
        _LOGGER.debug("Shutting down coordinator for %s", self.device_name)
        
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
