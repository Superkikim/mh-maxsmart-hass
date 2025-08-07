# maxsmart/device/core.py

import aiohttp
import asyncio
import logging
from ..const import (
    DEFAULT_STRIP_NAME,
    DEFAULT_PORT_NAMES,
    CMD_GET_DEVICE_DATA,
    CMD_GET_DEVICE_IDS,
    DEVICE_ERROR_MESSAGES,
)
from ..utils import get_user_locale, log_message
from ..discovery import MaxSmartDiscovery
from ..exceptions import ConnectionError as MaxSmartConnectionError, DiscoveryError, DeviceOperationError
from .commands import CommandMixin
from .control import ControlMixin
from .statistics import StatisticsMixin
from .configuration import ConfigurationMixin
from .time import TimeMixin
from .hardware import HardwareMixin
from .polling import AdaptivePollingMixin


class MaxSmartDevice(
    CommandMixin, 
    ControlMixin, 
    StatisticsMixin, 
    ConfigurationMixin, 
    TimeMixin,
    HardwareMixin,
    AdaptivePollingMixin
):
    """
    Main MaxSmart device class with dual protocol support (HTTP and UDP V3).
    
    This class combines all device functionality and automatically routes commands
    to the appropriate protocol based on device capabilities.
    """

    # Session management configuration
    DEFAULT_CONNECTOR_LIMIT = 10
    DEFAULT_CONNECTOR_LIMIT_PER_HOST = 5
    SESSION_TIMEOUT = 30.0  # seconds
    
    def __init__(self, ip_address, protocol=None, auto_polling=False):
        """
        Initialize a MaxSmart device with protocol detection.
        
        Args:
            ip_address (str): IP address of the device
            protocol (str): Force specific protocol ('http', 'udp_v3', or None for auto-detect)
            auto_polling (bool): Start polling automatically after initialization
        """
        # Validate IP address format
        import socket
        try:
            socket.inet_aton(ip_address)
        except socket.error:
            raise DeviceOperationError(
                user_locale=get_user_locale(),
                ip=ip_address,
                detail=f"Invalid IP address format: {ip_address}"
            )
            
        self.ip = ip_address
        self.user_locale = get_user_locale()
        self.protocol = protocol  # 'http', 'udp_v3', or None for auto-detect
        self._auto_polling = auto_polling

        # Initialize default values
        self.strip_name = DEFAULT_STRIP_NAME
        self.port_names = DEFAULT_PORT_NAMES

        # Store device information
        self.sn = None
        self.name = None
        self.version = None
        
        # Firmware-specific conversion factor (auto-detected after initialization)
        self._watt_multiplier = 1.0  # Default
        self._watt_format = "unknown"  # Will be detected

        # Session management
        self._session = None
        self._is_initialized = False

        # Initialize all mixins
        super().__init__()

    @property
    def session(self):
        """
        Get aiohttp session for HTTP protocol, creating it if necessary.
        Only used for HTTP protocol.
        """
        if self.protocol == 'udp_v3':
            # UDP V3 doesn't need HTTP session
            return None
            
        if self._session is None or self._session.closed:
            # Create connector with reasonable limits
            connector = aiohttp.TCPConnector(
                limit=self.DEFAULT_CONNECTOR_LIMIT,
                limit_per_host=self.DEFAULT_CONNECTOR_LIMIT_PER_HOST,
                ttl_dns_cache=300,
                use_dns_cache=True,
                force_close=True,
                enable_cleanup_closed=True
            )
            
            timeout = aiohttp.ClientTimeout(
                total=self.SESSION_TIMEOUT,
                connect=10.0,
                sock_read=10.0
            )
            
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={'User-Agent': 'MaxSmart-Python/2.0.5'}
            )
            
            logging.debug(f"Created HTTP session for device {self.ip}")
                
        return self._session

    async def initialize_device(self, start_polling=None):
        """
        Initialize device and auto-detect protocol if not specified.
        
        Args:
            start_polling (bool): Override auto_polling setting
        """
        if self._is_initialized:
            logging.debug(f"Device {self.ip} already initialized")
            should_start_polling = start_polling if start_polling is not None else self._auto_polling
            if should_start_polling and not self.is_polling:
                await self.start_adaptive_polling()
            return
        
        try:
            # Auto-detect protocol if not specified
            if self.protocol is None:
                self.protocol = await self._auto_detect_protocol()
                logging.debug(f"Auto-detected protocol: {self.protocol}")
            
            # Initialize based on protocol
            if self.protocol == 'http':
                await self._initialize_http_device()
            elif self.protocol == 'udp_v3':
                await self._initialize_udp_v3_device()
            else:
                raise MaxSmartConnectionError(
                    user_locale=self.user_locale,
                    error_key="ERROR_NETWORK_ISSUE",
                    ip=self.ip,
                    detail=f"Unsupported protocol: {self.protocol}"
                )
            
            self._is_initialized = True
            logging.debug(f"Device initialized: {self.ip} - Protocol: {self.protocol}")
            
            # Start polling if requested
            should_start_polling = start_polling if start_polling is not None else self._auto_polling
            if should_start_polling:
                await self.start_adaptive_polling()
            
        except Exception as e:
            logging.error(f"Device initialization failed for {self.ip}: {e}")
            raise
    
    async def _auto_detect_protocol(self):
        """
        Auto-detect device protocol by testing HTTP first, then UDP V3.
        
        Returns:
            str: 'http', 'udp_v3', or raises exception if neither works
        """
        # First, get device info from discovery to get serial number
        try:
            discovery_devices = await MaxSmartDiscovery.discover_maxsmart(ip=self.ip, enhance_with_hardware_ids=False)
            if discovery_devices:
                device_info = discovery_devices[0]
                self.sn = device_info.get("sn")
                self.name = device_info.get("name")
                self.version = device_info.get("ver")
            else:
                raise MaxSmartConnectionError(
                    user_locale=self.user_locale,
                    error_key="ERROR_DEVICE_NOT_FOUND",
                    ip=self.ip,
                    detail="Device not found during discovery"
                )
        except Exception as e:
            raise MaxSmartConnectionError(
                user_locale=self.user_locale,
                error_key="ERROR_DISCOVERY_FAILED",
                ip=self.ip,
                detail=f"Failed to get device info: {e}"
            )
        
        # Test HTTP protocol first
        if await self._test_http_protocol():
            return 'http'
        
        # Test UDP V3 protocol
        if await self._test_udp_v3_protocol():
            return 'udp_v3'
        
        # Neither protocol works
        raise MaxSmartConnectionError(
            user_locale=self.user_locale,
            error_key="ERROR_NETWORK_ISSUE",
            ip=self.ip,
            detail="Device does not respond to HTTP or UDP V3 protocols"
        )
    
    async def _test_http_protocol(self):
        """Test if device responds to HTTP commands."""
        try:
            # Temporarily set protocol to http for testing
            old_protocol = getattr(self, 'protocol', None)
            self.protocol = 'http'
            
            # Try a simple HTTP command
            response = await self._send_command(CMD_GET_DEVICE_DATA)
            
            # If we get here, HTTP works
            return True
            
        except Exception as e:
            logging.debug(f"HTTP protocol test failed for {self.ip}: {e}")
            return False
        finally:
            # Restore original protocol
            self.protocol = old_protocol
    
    async def _test_udp_v3_protocol(self):
        """Test if device responds to UDP V3 commands."""
        try:
            # Need serial number for UDP V3 test
            if not self.sn:
                return False
                
            # Temporarily set protocol to udp_v3 for testing
            old_protocol = getattr(self, 'protocol', None)
            self.protocol = 'udp_v3'
            
            # Try a simple UDP V3 command
            response = await self._send_command(CMD_GET_DEVICE_DATA)
            
            # If we get here, UDP V3 works
            return True
            
        except Exception as e:
            logging.debug(f"UDP V3 protocol test failed for {self.ip}: {e}")
            return False
        finally:
            # Restore original protocol
            self.protocol = old_protocol
    
    async def _initialize_http_device(self):
        """Initialize device using HTTP protocol."""
        # Test HTTP connectivity and get data for format detection
        response = await self._send_command(CMD_GET_DEVICE_DATA)
        data = response.get("data", {})

        if not data:
            raise MaxSmartConnectionError(
                user_locale=self.user_locale,
                error_key="ERROR_MISSING_EXPECTED_DATA",
                ip=self.ip,
                detail="No data received from HTTP device"
            )

        # Auto-detect watt format
        self._detect_watt_format(data)
        
        # Retrieve port names if not already done during discovery
        if not getattr(self, '_is_temp_device', False):
            try:
                await self.retrieve_port_names()
            except Exception as e:
                logging.debug(f"Could not retrieve port names for HTTP device {self.ip}: {e}")
    
    async def _initialize_udp_v3_device(self):
        """Initialize device using UDP V3 protocol."""
        # Test UDP V3 connectivity and get data for format detection
        response = await self._send_command(CMD_GET_DEVICE_DATA)
        data = response.get("data", {})

        if not data:
            raise MaxSmartConnectionError(
                user_locale=self.user_locale,
                error_key="ERROR_MISSING_EXPECTED_DATA",
                ip=self.ip,
                detail="No data received from UDP V3 device"
            )

        # Auto-detect watt format (UDP V3 should be integer milliwatts)
        self._detect_watt_format(data)
        
        # UDP V3 devices don't support port name retrieval via commands
        # Keep default port names
        logging.debug(f"UDP V3 device {self.ip} - using default port names")
    
    def _detect_watt_format(self, data):
        """Detect and configure watt value format based on sample data."""
        watt_values = data.get("watt", [])
        
        if watt_values:
            sample_value = watt_values[0]
            logging.debug(f"Watt format detection sample: {sample_value} (type: {type(sample_value)})")
            
            if isinstance(sample_value, (float, str)):
                # Float or string = watts
                self._watt_multiplier = 1.0
                self._watt_format = "float_watt"
            elif isinstance(sample_value, int):
                # Integer = milliwatts, convert to watts
                self._watt_multiplier = 0.001
                self._watt_format = "int_milliwatt"
            else:
                # Unknown type - keep raw value for debugging
                self._watt_multiplier = 1.0
                self._watt_format = "unknown_format"
                log_message(DEVICE_ERROR_MESSAGES, "UNKNOWN_WATT_FORMAT", 
                           self.user_locale, level=logging.WARNING, 
                           ip=self.ip, data_type=type(sample_value).__name__, sample_value=sample_value)
        else:
            # No watt data - API may have changed
            self._watt_multiplier = 1.0
            self._watt_format = "no_data"
            log_message(DEVICE_ERROR_MESSAGES, "ERROR_WATT_DATA_NOT_FOUND",
                       self.user_locale, level=logging.ERROR, ip=self.ip)

    def _convert_watt(self, raw_watt):
        """
        Convert raw watt value based on detected format.
        
        Args:
            raw_watt: Raw watt value from device
            
        Returns:
            float: Converted watt value
        """
        return float(raw_watt) * self._watt_multiplier
        
    def _convert_watt_list(self, raw_watt_list):
        """
        Convert a list of raw watt values based on detected format.
        
        Args:
            raw_watt_list: List of raw watt values from device
            
        Returns:
            list: List of converted watt values
        """
        return [self._convert_watt(watt) for watt in raw_watt_list]

    async def setup_realtime_monitoring(self, consumption_callback=None, state_callback=None):
        """
        Setup real-time monitoring with consumption and state change detection.
        Works with both HTTP and UDP V3 protocols.
        
        Args:
            consumption_callback: Called when consumption changes significantly (>1W)
            state_callback: Called when port states change
        """
        if not self.is_polling:
            await self.start_adaptive_polling()
            
        # Setup change detection callbacks
        if consumption_callback or state_callback:
            await self._setup_change_detection(consumption_callback, state_callback)
            
    async def setup_realtime_monitoring_with_baseline(self, consumption_callback=None, state_callback=None, initial_watt=None, initial_switch=None):
        """
        Setup real-time monitoring with provided baseline values.
        Works with both HTTP and UDP V3 protocols.
        
        Args:
            consumption_callback: Called when consumption changes significantly
            state_callback: Called when port states change
            initial_watt: Initial watt values to use as baseline
            initial_switch: Initial switch states to use as baseline
        """
        if not self.is_polling:
            await self.start_adaptive_polling()
            
        # Setup change detection callbacks with baseline
        if consumption_callback or state_callback:
            await self._setup_change_detection_with_baseline(
                consumption_callback, 
                state_callback, 
                initial_watt or [0] * 6, 
                initial_switch or [0] * 6
            )

    async def _setup_change_detection_with_baseline(self, consumption_callback, state_callback, initial_watt, initial_switch):
        """Setup callbacks for detecting consumption and state changes with baseline."""
        last_data = {
            "watt": initial_watt[:6] if initial_watt else [0] * 6, 
            "switch": initial_switch[:6] if initial_switch else [0] * 6
        }
        
        async def change_detector(poll_data):
            try:
                device_data = poll_data.get("device_data", {})
                current_watt = device_data.get("watt", [])
                current_switch = device_data.get("switch", [])
                
                # Detect significant consumption changes (>1W)
                if consumption_callback and current_watt and len(current_watt) >= 6:
                    for i, (curr, prev) in enumerate(zip(current_watt, last_data["watt"])):
                        if abs(curr - prev) > 1.0:
                            await self._safe_callback(consumption_callback, {
                                "port": i + 1,
                                "port_name": self.port_names[i] if i < len(self.port_names) else f"Port {i+1}",
                                "previous_watt": prev,
                                "current_watt": curr,
                                "change": curr - prev,
                                "timestamp": poll_data["timestamp"]
                            })
                            
                # Detect state changes
                if state_callback and current_switch and len(current_switch) >= 6:
                    for i, (curr, prev) in enumerate(zip(current_switch, last_data["switch"])):
                        if curr != prev:
                            await self._safe_callback(state_callback, {
                                "port": i + 1,
                                "port_name": self.port_names[i] if i < len(self.port_names) else f"Port {i+1}",
                                "previous_state": prev,
                                "current_state": curr,
                                "state_text": "ON" if curr else "OFF",
                                "timestamp": poll_data["timestamp"]
                            })
                            
                # Update last known values ONLY if we have valid data
                if current_watt and len(current_watt) >= 6:
                    last_data["watt"] = current_watt[:6]
                if current_switch and len(current_switch) >= 6:
                    last_data["switch"] = current_switch[:6]
                    
            except Exception as e:
                logging.error(f"Error in change detector: {e}")
                
        self.register_poll_callback("change_detector", change_detector)
        
    async def _safe_callback(self, callback, data):
        """Safely execute a callback with error handling."""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(data)
            else:
                callback(data)
        except Exception as e:
            logging.warning(f"Callback error: {e}")

    async def health_check(self):
        """
        Perform a basic health check to verify device connectivity.
        Works with both HTTP and UDP V3 protocols.
        
        Returns:
            dict: Health check results with status and response time
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Try to get basic device data as health check
            await self.get_data()
            response_time = asyncio.get_event_loop().time() - start_time
            
            return {
                "status": "healthy",
                "response_time": round(response_time * 1000, 2),  # milliseconds
                "polling_active": self.is_polling,
                "protocol": self.protocol,
                "device": {
                    "name": self.name,
                    "ip": self.ip,
                    "sn": self.sn,
                    "firmware": self.version
                }
            }
            
        except Exception as e:
            response_time = asyncio.get_event_loop().time() - start_time
            return {
                "status": "unhealthy",
                "response_time": round(response_time * 1000, 2),
                "polling_active": self.is_polling,
                "protocol": self.protocol,
                "error": str(e),
                "device": {
                    "name": self.name,
                    "ip": self.ip,
                    "sn": self.sn,
                    "firmware": self.version
                }
            }
        
    def __repr__(self):
        """String representation of the device."""
        init_status = "initialized" if self._is_initialized else "not initialized"
        polling_status = "polling" if self.is_polling else "not polling"
        protocol_info = f"protocol={self.protocol}" if self.protocol else "protocol=unknown"
        return (
            f"MaxSmartDevice(ip={self.ip}, sn={self.sn}, name={self.name}, "
            f"version={self.version}, {protocol_info}, {init_status}, {polling_status})"
        )

    async def close(self):
        """
        Close sessions and cleanup resources for both protocols.
        """
        # Stop polling first
        await self.stop_adaptive_polling()
        
        # Close HTTP session if using HTTP protocol
        if self.protocol == 'http' and self._session and not self._session.closed:
            try:
                await self._session.close()
                logging.debug(f"Closed HTTP session for device {self.ip}")
            except Exception as e:
                logging.debug(f"Error closing HTTP session for device {self.ip}: {e}")
            finally:
                self._session = None
                
        self._is_initialized = False
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize_device()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup."""
        await self.close()