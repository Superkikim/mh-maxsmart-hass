"""Polling management for MaxSmart devices."""

import asyncio
import logging
import time
from typing import Dict, Any, Optional

from ..messages import log_error_recorded

_LOGGER = logging.getLogger(__name__)


class PollingManager:
    """Manages intelligent polling and retry logic for MaxSmart devices."""
    
    def __init__(self, coordinator):
        """Initialize polling manager."""
        self.coordinator = coordinator
        self.device_name = coordinator.device_name
        self._periodic_task = None
        self._offline_retry_task = None
        self._error_detection_task = None
    
    async def on_poll_data(self, poll_data: Dict[str, Any]) -> None:
        """Callback for successful polling data from maxsmart intelligent polling."""
        try:
            # Record successful poll for error tracking
            self.coordinator.error_tracker.record_successful_poll()
            
            # Update coordinator data
            self.coordinator.async_set_updated_data(poll_data)
            
            _LOGGER.debug("%s polling callback: Data updated successfully", self.device_name)
            
        except Exception as err:
            _LOGGER.error("%s polling callback error: %s", self.device_name, err)
    
    def start_periodic_polling(self) -> None:
        """Start periodic polling when callback system is not available."""
        if self._periodic_task is None or self._periodic_task.done():
            self._periodic_task = asyncio.create_task(self._periodic_poll_loop())
            _LOGGER.debug("%s periodic polling started", self.device_name)
    
    async def _periodic_poll_loop(self) -> None:
        """Periodic polling loop for new API without callbacks."""
        try:
            while not self.coordinator._shutdown_event.is_set():
                try:
                    if self.coordinator.device and self.coordinator._initialized:
                        # Get fresh data from device
                        data = await self.coordinator.device.get_data()
                        if data:
                            await self.on_poll_data(data)
                        
                    await asyncio.sleep(30)  # Poll every 30 seconds
                    
                except Exception as err:
                    _LOGGER.debug("%s periodic polling error: %s", self.device_name, err)
                    await asyncio.sleep(60)  # Longer wait on error
                    
        except asyncio.CancelledError:
            _LOGGER.debug("%s periodic polling cancelled", self.device_name)
        except Exception as err:
            _LOGGER.error("%s periodic polling failed: %s", self.device_name, err)
    
    def start_offline_retry(self) -> None:
        """Start periodic retry for offline devices."""
        if self._offline_retry_task is None or self._offline_retry_task.done():
            self._offline_retry_task = asyncio.create_task(self._offline_retry_loop())
            _LOGGER.warning("🔄 OFFLINE RETRY: %s - Starting retry loop", self.device_name)
    
    async def _offline_retry_loop(self) -> None:
        """Conservative retry loop for offline devices with integrated IP recovery."""
        try:
            offline_start_time = time.time()
            retry_interval = 60.0  # Start with 60 seconds
            max_interval = 300.0   # Max 5 minutes
            
            _LOGGER.warning("🔄 OFFLINE RETRY: %s - Starting retry loop (interval=%ds, max=%ds)",
                           self.device_name, retry_interval, max_interval)

            # Set offline start time for IP recovery timeline
            self.coordinator.ip_recovery.set_device_offline_start(offline_start_time)

            _LOGGER.warning("🔄 OFFLINE RETRY LOOP: %s - About to enter while loop, initialized=%s",
                           self.device_name, self.coordinator._initialized)

            while not self.coordinator._initialized:
                _LOGGER.warning("🔄 OFFLINE RETRY LOOP: %s - Starting iteration, waiting %ds", self.device_name, retry_interval)
                await asyncio.sleep(retry_interval)
                current_time = time.time()

                _LOGGER.warning("🔄 OFFLINE RETRY LOOP: %s - Sleep completed, starting attempt", self.device_name)

                try:
                    # Try original IP first
                    success = await self.coordinator._try_connect_at_ip(self.coordinator.device_ip)

                    if success:
                        _LOGGER.info("✅ %s - Connection restored", self.device_name)
                        await self.coordinator._complete_successful_setup()
                        return

                    # Original IP failed - record error for smart logging
                    should_log = self.coordinator.error_tracker.record_error("connection_refused")
                    log_error_recorded(self.device_name, "connection_refused",
                                     self.coordinator.error_tracker.consecutive_errors, should_log)

                    # 🚀 ARP CHECK: Check for IP change on FIRST failure only
                    if self.coordinator.error_tracker.consecutive_errors == 1 and self.coordinator.mac_address:
                        _LOGGER.debug("🔍 FIRST FAILURE: %s - Performing ARP check", self.device_name)
                        await self.coordinator.ip_recovery_manager.immediate_arp_check()
                        # If ARP found new IP and changed it, the device will be reinitialized
                        # and this loop will exit, so we can continue to next iteration
                        continue

                    # NEW: Check if IP recovery should be attempted based on consecutive failures
                    _LOGGER.warning("🔍 IP RECOVERY CHECK: %s - Errors=%d, threshold=3, MAC=%s",
                                 self.device_name, self.coordinator.error_tracker.consecutive_errors,
                                 self.coordinator.mac_address[:8] + "..." if self.coordinator.mac_address else "None")

                    if self.coordinator.error_tracker.consecutive_errors >= 3:
                        can_recover = self.coordinator.ip_recovery.can_attempt_recovery(current_time)

                        if can_recover:
                            new_ip = await self._attempt_runtime_ip_recovery(current_time)
                            if new_ip:
                                success = await self.coordinator._try_connect_at_ip(new_ip)
                                if success:
                                    await self.coordinator.ip_recovery_manager._update_device_ip(new_ip)
                                    await self.coordinator._complete_successful_setup()
                                    return
                        else:
                            recovery_status = self.coordinator.ip_recovery.get_status()
                            _LOGGER.debug("⏳ IP RECOVERY: %s - Not ready yet - %s", self.device_name, recovery_status)
                    else:
                        _LOGGER.debug("⏳ IP RECOVERY CHECK: %s - Need %d more errors (current: %d)",
                                     self.device_name, 3 - self.coordinator.error_tracker.consecutive_errors,
                                     self.coordinator.error_tracker.consecutive_errors)

                    # Both failed - increase retry interval (normal retry logic continues)
                    old_interval = retry_interval
                    retry_interval = min(retry_interval * 1.5, max_interval)
                    _LOGGER.debug("%s Offline retry: Increasing retry interval %.1fs -> %.1fs",
                                 self.device_name, old_interval, retry_interval)

                except asyncio.CancelledError:
                    _LOGGER.debug("Offline retry loop cancelled for %s", self.device_name)
                    break
                except Exception as err:
                    _LOGGER.error("Offline retry attempt failed for %s: %s", self.device_name, err)
                    await asyncio.sleep(retry_interval)

        except asyncio.CancelledError:
            _LOGGER.debug("Offline retry loop cancelled for %s", self.device_name)
        except Exception as err:
            _LOGGER.error("Offline retry loop failed for %s: %s", self.device_name, err)

    async def _attempt_runtime_ip_recovery(self, current_time: float) -> Optional[str]:
        """Attempt conservative IP recovery during runtime with final exhaustion handling."""
        try:
            # Start recovery attempt
            self.coordinator.ip_recovery.start_attempt(current_time)
            
            # Attempt IP recovery
            new_ip = await self.coordinator.ip_recovery_manager.recover_device_ip()
            
            if new_ip:
                _LOGGER.info("🔍 IP RECOVERY: %s - Found new IP %s", self.device_name, new_ip)
                return new_ip
            else:
                _LOGGER.debug("🔍 IP RECOVERY: %s - No new IP found", self.device_name)
                
                # Check if we've exhausted all attempts
                if self.coordinator.ip_recovery.attempts >= self.coordinator.ip_recovery.max_attempts:
                    _LOGGER.warning("⏰ IP RECOVERY: %s - EXHAUSTED all %d attempts, giving up", 
                                   self.device_name, self.coordinator.ip_recovery.max_attempts)
                
                return None
                
        except Exception as e:
            _LOGGER.error("🔍 IP RECOVERY: %s - Exception during recovery: %s", self.device_name, e)
            return None

    def start_conservative_error_detection(self) -> None:
        """Start background task with conservative error detection."""
        if self._error_detection_task is None or self._error_detection_task.done():
            self._error_detection_task = asyncio.create_task(self._conservative_error_detection_loop())
            _LOGGER.debug("%s Error detection: Starting conservative error detection loop", self.device_name)

    async def _conservative_error_detection_loop(self) -> None:
        """Conservative error detection loop with integrated IP recovery timeline."""
        try:
            while not self.coordinator._shutdown_event.is_set():
                await asyncio.sleep(120)  # Check every 2 minutes
                
                current_time = time.time()
                
                # Only check if device is supposed to be online
                if self.coordinator._initialized and self.coordinator.device:
                    # Check if device is responding
                    try:
                        # Simple ping test
                        is_responding = await self.coordinator._try_connect_at_ip(self.coordinator.device_ip)
                        
                        if not is_responding:
                            # Device not responding - record error
                            should_log = self.coordinator.error_tracker.record_error("connection_refused")
                            log_error_recorded(self.device_name, "connection_refused",
                                             self.coordinator.error_tracker.consecutive_errors, should_log)
                            
                            # Check if IP recovery attempt should be made
                            can_recover = self.coordinator.ip_recovery.can_attempt_recovery(current_time)
                            _LOGGER.debug("%s Error detection: IP recovery check result: %s", self.device_name, can_recover)
                            
                            if can_recover:
                                _LOGGER.debug("%s Error detection: TRIGGERING IP recovery attempt", self.device_name)
                                await self._attempt_runtime_ip_recovery(current_time)
                            else:
                                recovery_status = self.coordinator.ip_recovery.get_status()
                                _LOGGER.debug("%s Error detection: IP recovery not ready - %s", self.device_name, recovery_status)
                        else:
                            _LOGGER.debug("%s Error detection: Device status OK", self.device_name)
                    
                    except Exception as err:
                        _LOGGER.debug("%s Error detection: Check failed: %s", self.device_name, err)
                
        except asyncio.CancelledError:
            _LOGGER.debug("%s Error detection: Loop cancelled", self.device_name)
        except Exception as err:
            _LOGGER.error("%s Error detection: Loop failed: %s", self.device_name, err)

    async def stop_all_tasks(self) -> None:
        """Stop all polling and retry tasks."""
        tasks_to_cancel = []
        
        if self._periodic_task and not self._periodic_task.done():
            tasks_to_cancel.append(self._periodic_task)
        
        if self._offline_retry_task and not self._offline_retry_task.done():
            tasks_to_cancel.append(self._offline_retry_task)
        
        if self._error_detection_task and not self._error_detection_task.done():
            tasks_to_cancel.append(self._error_detection_task)
        
        for task in tasks_to_cancel:
            task.cancel()
        
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
            _LOGGER.debug("%s Polling manager: Stopped %d tasks", self.device_name, len(tasks_to_cancel))
