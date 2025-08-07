# exceptions.py
import logging

from .const import (
    DISCOVERY_ERROR_MESSAGES, 
    DISCOVERY_LOGGING_MESSAGES, 
    DEVICE_ERROR_MESSAGES, 
    CONNECTION_ERROR_MESSAGES, 
    DEVICE_STATE_ERROR_MESSAGES,
    FIRMWARE_ERROR_MESSAGES,
    STATE_ERROR_MESSAGES,
    IN_DEVICE_NAME_VERSION
)

from .utils import (
    get_user_message,
    log_message,  # Ensure proper imports for localization and logging
)

class MaxSmartError(Exception):
    """Base class for all MaxSmart exceptions."""
    
    def __init__(self, message, user_locale=None, **kwargs):
        self.user_locale = user_locale
        self.error_details = kwargs
        super().__init__(message)
        
    def log_error(self, log_message_key, logging_messages_dict):
        """Logs the error message using the provided log message key."""
        if self.user_locale:
            log_message(logging_messages_dict, log_message_key, self.user_locale, **self.error_details)

class DiscoveryError(MaxSmartError):
    """Exception raised when device discovery fails."""

    def __init__(self, error_key, user_locale, **kwargs):
        self.error_key = error_key
        self.user_locale = user_locale
        
        # Step 1: Get the localized error message
        message = get_user_message(DISCOVERY_ERROR_MESSAGES, self.error_key, self.user_locale, **kwargs)
        
        # Step 2: Log the localized message with context
        if error_key == "ERROR_NO_DEVICES_FOUND":
            log_key = "LOG_NO_DEVICES_FOUND"
        elif error_key == "ERROR_UDP_TIMEOUT":
            log_key = "LOG_UDP_TIMEOUT"
        elif error_key == "ERROR_INVALID_IP_FORMAT":
            log_key = "LOG_DISCOVERY_ERROR"
            kwargs["error"] = message
        elif error_key == "ERROR_INVALID_PARAMETERS":
            log_key = "LOG_DISCOVERY_ERROR"
            kwargs["error"] = message
        else:
            log_key = "LOG_DISCOVERY_ERROR"
            kwargs["error"] = message
            
        log_message(DISCOVERY_LOGGING_MESSAGES, log_key, user_locale, level=logging.ERROR, **kwargs)

        # Step 3: Raise the error with the localized message
        super().__init__(f"Discovery error: {message}", user_locale, **kwargs)

class UdpTimeoutInfo(MaxSmartError):
    """Exception raised when a UDP timeout occurs."""

    def __init__(self, user_locale, **kwargs):
        self.user_locale = user_locale

        # Get the localized message for the timeout
        message = get_user_message(DISCOVERY_ERROR_MESSAGES, "ERROR_UDP_TIMEOUT", self.user_locale, **kwargs)
        
        # Log the localized message
        log_message(DISCOVERY_LOGGING_MESSAGES, "LOG_UDP_TIMEOUT", self.user_locale, level=logging.INFO, **kwargs)

        # Instead of raising an error, initialize with the message for further usage if needed
        super().__init__(message, user_locale, **kwargs)
        
class ConnectionError(MaxSmartError):
    """Exception raised for errors related to network connections."""
    
    def __init__(self, user_locale, error_key="ERROR_NETWORK_ISSUE", **kwargs):
        self.user_locale = user_locale
        self.error_key = error_key

        # Use the utility function to get the localized error message
        message = get_user_message(CONNECTION_ERROR_MESSAGES, self.error_key, self.user_locale, **kwargs)
        
        # Log the localized message using the utility function
        log_kwargs = {"ip": kwargs.get("ip", "unknown"), "error": message}
        log_message(DISCOVERY_LOGGING_MESSAGES, "LOG_CONNECTION_ERROR", self.user_locale, 
                   level=logging.ERROR, **log_kwargs)

        super().__init__(message, user_locale, **kwargs)

class DeviceError(MaxSmartError):
    """Exception raised for errors related to device operations."""

    def __init__(self, error_key, user_locale, **kwargs):
        self.error_key = error_key
        self.user_locale = user_locale
        
        # Use the utility function to get the localized error message
        message = get_user_message(DEVICE_ERROR_MESSAGES, self.error_key, self.user_locale, **kwargs)
        
        # Log the localized message using the utility function (if applicable)
        log_message(DEVICE_STATE_ERROR_MESSAGES, "LOG_COMMAND_RETRY", self.user_locale, 
                   level=logging.ERROR, command=f"Device operation: {error_key}", **kwargs)

        super().__init__(f"Device error: {message}", user_locale, **kwargs)

class CommandError(MaxSmartError):
    """Exception raised for errors in command execution."""
    
    def __init__(self, error_key, user_locale, **kwargs):
        self.user_locale = user_locale
        self.error_key = error_key
        
        # Use the utility function to get the localized error message
        message = get_user_message(DEVICE_ERROR_MESSAGES, self.error_key, self.user_locale, **kwargs)

        # Log the localized message using the utility function
        log_kwargs = {
            "ip": kwargs.get("ip", "unknown"),
            "command": f"Command: {error_key}",
            "attempt": 1,
            "max_attempts": 3
        }
        log_message(DEVICE_STATE_ERROR_MESSAGES, "LOG_COMMAND_RETRY", self.user_locale, 
                   level=logging.ERROR, **log_kwargs)

        super().__init__(message, user_locale, **kwargs)

    @staticmethod
    def get_error_message(error_key, user_locale, **kwargs):
        """Get formatted error message without raising exception."""
        return get_user_message(DEVICE_ERROR_MESSAGES, error_key, user_locale, **kwargs)

class DeviceNotFoundError(MaxSmartError):
    """Exception raised when a specific device is not found during discovery."""

    def __init__(self, device_name, user_locale, **kwargs):
        self.device_name = device_name
        self.user_locale = user_locale
        
        # Add device_name to kwargs for message formatting
        kwargs.update({"device_name": device_name})
        
        # Step 1: Get the localized error message
        error_key = "ERROR_NO_DEVICES_FOUND"
        message = get_user_message(DISCOVERY_ERROR_MESSAGES, error_key, self.user_locale, **kwargs)
        
        # Step 2: Log the localized message
        log_key = "LOG_DEVICE_NOT_FOUND"
        log_message(DEVICE_STATE_ERROR_MESSAGES, log_key, self.user_locale, 
                   level=logging.ERROR, **kwargs)

        # Step 3: Raise the error with the localized message
        super().__init__(message, user_locale, **kwargs)

class DeviceTimeoutError(MaxSmartError):
    """Exception raised when a device does not respond in time."""

    def __init__(self, device_name, user_locale, timeout=None, **kwargs):
        self.device_name = device_name
        self.user_locale = user_locale

        # Add device details to kwargs
        kwargs.update({
            "device_name": device_name,
            "timeout": timeout or "unknown"
        })

        # Step 1: Get the localized error message
        error_key = "ERROR_DEVICE_TIMEOUT"
        message = get_user_message(DEVICE_ERROR_MESSAGES, error_key, self.user_locale, **kwargs)

        # Step 2: Log the localized message
        log_key = "LOG_DEVICE_TIMEOUT"
        log_message(DEVICE_STATE_ERROR_MESSAGES, log_key, self.user_locale, 
                   level=logging.ERROR, **kwargs)

        # Step 3: Raise the error with the localized message
        super().__init__(message, user_locale, **kwargs)
            
class DeviceOperationError(MaxSmartError):
    """Exception raised for invalid parameters during device operations."""

    def __init__(self, user_locale, **kwargs):
        self.user_locale = user_locale

        # Get the localized error message for invalid parameters
        error_key = "ERROR_INVALID_PARAMETERS"
        message = get_user_message(DEVICE_ERROR_MESSAGES, error_key, self.user_locale, **kwargs)

        # Log the localized message with proper parameters
        log_kwargs = {
            "ip": kwargs.get("ip", "unknown"),
            "command": "Device operation",
            "detail": kwargs.get("detail", "Invalid parameters")
        }
        log_message(DEVICE_STATE_ERROR_MESSAGES, "LOG_DEVICE_OPERATION", self.user_locale, 
                   level=logging.ERROR, **log_kwargs)

        # Raise the error with the localized message
        super().__init__(message, user_locale, **kwargs)

class FirmwareError(MaxSmartError):
    """Exception raised for issues related to firmware version."""
    
    def __init__(self, device_ip, firmware_version, user_locale, required_version, **kwargs):
        self.device_ip = device_ip
        self.firmware_version = firmware_version
        self.user_locale = user_locale
        self.required_version = required_version
        
        # Add all details to kwargs for message formatting
        kwargs.update({
            "ip": device_ip,
            "firmware_version": firmware_version,
            "required_version": required_version
        })
        
        error_key = "ERROR_FIRMWARE_NOT_SUPPORTED"
        message = get_user_message(FIRMWARE_ERROR_MESSAGES, error_key, self.user_locale, **kwargs)
        
        # Add specific firmware limitation info
        if self.firmware_version != IN_DEVICE_NAME_VERSION:
            message += f" Your firmware version {self.firmware_version} supports basic commands, but not port name management."
        else:
            message += f" Your firmware version {self.firmware_version} is not supported. Port name management requires firmware version {self.required_version}."
        
        log_message(DEVICE_STATE_ERROR_MESSAGES, "LOG_DEVICE_NOT_FOUND", self.user_locale, 
                    level=logging.WARNING, device_name=f"Device {device_ip}", **kwargs)

        super().__init__(message, user_locale, **kwargs)

class StateError(MaxSmartError):
    """Exception raised for errors related to device states."""

    def __init__(self, error_key="ERROR_STATE_INVALID", user_locale=None, **kwargs):
        self.user_locale = user_locale
        self.error_key = error_key
        
        # Step 1: Get the localized error message
        localized_message = get_user_message(STATE_ERROR_MESSAGES, error_key, user_locale, **kwargs)
        
        # Step 2: Log the localized message
        log_message(DEVICE_STATE_ERROR_MESSAGES, "LOG_STATE_CHANGE", user_locale, 
                   level=logging.ERROR, old_state="unknown", new_state="error", **kwargs)

        # Step 3: Raise the error with the localized message
        super().__init__(localized_message, user_locale, **kwargs)