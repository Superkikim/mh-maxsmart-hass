"""Error tracking and cascade detection for MaxSmart devices."""

import logging
import time
from typing import Dict, Any, Set

_LOGGER = logging.getLogger(__name__)


class NetworkCascadeDetector:
    """Detects network cascade failures to reduce log pollution."""
    
    _instance = None
    _cascade_devices: Set[str] = set()
    _cascade_start_time = None
    _cascade_logged = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def report_device_failure(cls, device_name: str) -> bool:
        """
        Report device failure and detect cascade.
        
        Args:
            device_name: Name of the failing device
            
        Returns:
            True if this is part of a cascade (suppress individual logging)
        """
        current_time = time.time()
        
        # Add device to cascade set
        cls._cascade_devices.add(device_name)
        
        # Set cascade start time if first device
        if cls._cascade_start_time is None:
            cls._cascade_start_time = current_time
        
        # Check if this qualifies as a cascade (2+ devices within 30 seconds)
        if len(cls._cascade_devices) >= 2:
            time_since_start = current_time - cls._cascade_start_time
            
            if time_since_start <= 30:  # 30 second window
                # This is a cascade - log once if not already logged
                if not cls._cascade_logged:
                    _LOGGER.warning("🌊 NETWORK CASCADE: Multiple MaxSmart devices failing")
                    cls._cascade_logged = True
                return True  # Suppress individual device logging
        
        return False  # Not a cascade, allow individual logging
    
    @classmethod
    def report_device_recovery(cls, device_name: str) -> bool:
        """
        Report device recovery.
        
        Args:
            device_name: Name of the recovering device
            
        Returns:
            True if cascade is ending
        """
        # Remove device from cascade set
        cls._cascade_devices.discard(device_name)
        
        # If no more devices in cascade, reset
        if len(cls._cascade_devices) == 0:
            if cls._cascade_logged:
                _LOGGER.info("✅ NETWORK CASCADE: All devices recovered")
                cls._reset_cascade()
                return True
        
        return False
    
    def _reset_cascade(self):
        """Reset cascade state."""
        self._cascade_devices.clear()
        self._cascade_start_time = None
        self._cascade_logged = False


class SmartErrorTracker:
    """Smart error tracking to prevent log pollution."""
    
    def __init__(self, device_name: str):
        """Initialize smart error tracker."""
        self.device_name = device_name
        self.consecutive_errors = 0
        self.last_error_time = 0
        self.last_error_type = None
        self.last_successful_poll = 0
        self.total_errors = 0
        self.error_types_count = {}
        
        # Logging control
        self.last_logged_error_time = 0
        self.log_interval = 60  # Log errors at most once per minute
        
        # Network cascade detector
        self.cascade_detector = NetworkCascadeDetector()
        
    def record_successful_poll(self) -> None:
        """Record a successful poll - resets error state."""
        # Report recovery to cascade detector if we had errors
        if self.consecutive_errors > 0:
            cascade_ending = self.cascade_detector.report_device_recovery(self.device_name)
            if not cascade_ending:
                _LOGGER.debug("✅ RECOVERY: %s - Back online after %d errors", 
                             self.device_name, self.consecutive_errors)
        
        # Reset error tracking
        self.consecutive_errors = 0
        self.last_error_type = None
        self.last_successful_poll = time.time()
    
    def record_error(self, error_type: str) -> bool:
        """
        Record an error and determine if it should be logged.
        
        Args:
            error_type: Type of error (connection_refused, timeout, etc.)
            
        Returns:
            True if this error should be logged, False to suppress
        """
        current_time = time.time()
        
        # Update error tracking
        self.consecutive_errors += 1
        self.total_errors += 1
        self.last_error_time = current_time
        self.last_error_type = error_type
        
        # Count error types
        self.error_types_count[error_type] = self.error_types_count.get(error_type, 0) + 1
        
        # Check for network cascade
        is_cascade = self.cascade_detector.report_device_failure(self.device_name)
        if is_cascade:
            return False  # Suppress logging during cascade
        
        # Check if we should log this error
        return self._should_log_error(current_time)
    
    def _should_log_error(self, current_time: float) -> bool:
        """Determine if an error should be logged to prevent spam."""
        # Always log first error
        if self.consecutive_errors == 1:
            self.last_logged_error_time = current_time
            return True
        
        # Log every 5th error
        if self.consecutive_errors % 5 == 0:
            self.last_logged_error_time = current_time
            return True
        
        # Log if enough time has passed since last log
        if current_time - self.last_logged_error_time >= self.log_interval:
            self.last_logged_error_time = current_time
            return True
        
        return False
    
    def is_device_considered_offline(self) -> bool:
        """Check if device should be considered offline."""
        # Device is offline if we have 3+ consecutive errors
        return self.consecutive_errors >= 3
    
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
