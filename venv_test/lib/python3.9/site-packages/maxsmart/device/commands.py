# device/commands.py

import json
import asyncio
import socket
import aiohttp
from ..exceptions import CommandError, ConnectionError as MaxSmartConnectionError
from ..const import (
    CMD_SET_PORT_STATE,
    CMD_GET_DEVICE_DATA,
    CMD_SET_PORT_NAME,
    CMD_GET_STATISTICS,
    CMD_GET_DEVICE_TIME,
    CMD_GET_DEVICE_IDS,
    UDP_PORT,
    RESPONSE_CODE_SUCCESS,
)


class CommandMixin:
    """Mixin class providing unified command sending for both HTTP and UDP V3 protocols."""
    
    # Command timeout and retry configuration
    DEFAULT_TIMEOUT = 10.0  # seconds
    RETRY_COUNT = 3
    RETRY_DELAY = 1.0  # seconds between retries
    
    # UDP V3 specific configuration
    UDP_V3_TIMEOUT = 5.0
    UDP_V3_RETRIES = 3
    
    # Command mapping: HTTP -> UDP V3
    HTTP_TO_UDP_V3_COMMANDS = {
        CMD_SET_PORT_STATE: 20,  # HTTP 200 -> UDP V3 20
        CMD_GET_DEVICE_DATA: 90, # HTTP 511 -> UDP V3 90
        # Note: Other commands (statistics, time, etc.) not supported in UDP V3
    }
    
    async def _send_command(self, cmd, params=None, timeout=None, retries=None):
        """
        Send a command to the device using the appropriate protocol (HTTP or UDP V3).

        :param cmd: Command identifier (e.g., 511, 200, 201, 124).
        :param params: Additional parameters for the command (optional).
        :param timeout: Request timeout in seconds (default: 10s).
        :param retries: Number of retry attempts (default: 3).
        :return: Response from the device as JSON.
        
        :raises CommandError: For command validation or execution errors
        :raises MaxSmartConnectionError: For network/connectivity issues
        """
        # Route to appropriate protocol
        if hasattr(self, 'protocol') and self.protocol == 'udp_v3':
            return await self._send_udp_v3_command(cmd, params, timeout)
        else:
            return await self._send_http_command(cmd, params, timeout, retries)
    
    async def _send_http_command(self, cmd, params=None, timeout=None, retries=None):
        """
        Send a command to the device via HTTP (existing logic).

        :param cmd: Command identifier (e.g., 511, 200, 201, 124).
        :param params: Additional parameters for the command (optional).
        :param timeout: Request timeout in seconds (default: 10s).
        :param retries: Number of retry attempts (default: 3).
        :return: Response from the device as JSON.
        
        :raises CommandError: For command validation or execution errors
        :raises MaxSmartConnectionError: For network/connectivity issues
        """
        # Use default values if not specified
        if timeout is None:
            timeout = self.DEFAULT_TIMEOUT
        if retries is None:
            retries = self.RETRY_COUNT
            
        # Validate the command
        valid_commands = {
            CMD_GET_DEVICE_DATA,
            CMD_GET_STATISTICS,
            CMD_SET_PORT_STATE,
            CMD_SET_PORT_NAME,
            CMD_GET_DEVICE_TIME,
            CMD_GET_DEVICE_IDS,
        }
        if cmd not in valid_commands:
            raise CommandError(
                "ERROR_INVALID_PARAMETERS",
                self.user_locale,
                ip=self.ip,
                detail=f"Invalid HTTP command {cmd}. Must be one of {', '.join(map(str, valid_commands))}."
            )

        # Construct the URL with parameters, if any
        url = f"http://{self.ip}/?cmd={cmd}"
        if params:
            try:
                url += f"&json={json.dumps(params, separators=(',', ':'))}"
            except (TypeError, ValueError) as e:
                raise CommandError(
                    "ERROR_INVALID_PARAMETERS",
                    self.user_locale,
                    ip=self.ip,
                    detail=f"Failed to serialize parameters: {e}"
                )

        # Retry loop with exponential backoff
        last_exception = None
        for attempt in range(retries + 1):
            try:
                # Create timeout configuration
                timeout_config = aiohttp.ClientTimeout(
                    total=timeout,
                    connect=timeout / 2,  # Connection timeout is half of total
                    sock_read=timeout / 2  # Socket read timeout
                )
                
                # Make the HTTP request
                async with self.session.get(url, timeout=timeout_config) as response:
                    # Check HTTP status
                    if response.status != RESPONSE_CODE_SUCCESS:
                        content = await response.text()
                        if response.status == 404:
                            raise MaxSmartConnectionError(
                                self.user_locale,
                                "ERROR_DEVICE_NOT_FOUND",
                                ip=self.ip,
                                detail=f"Device HTTP endpoint not found (HTTP 404)"
                            )
                        elif response.status >= 500:
                            raise MaxSmartConnectionError(
                                self.user_locale,
                                "ERROR_HTTP_ERROR", 
                                ip=self.ip,
                                status=response.status,
                                detail=f"Device server error: {content[:100]}"
                            )
                        else:
                            raise CommandError(
                                "ERROR_HTTP_ERROR",
                                self.user_locale,
                                ip=self.ip,
                                status=response.status,
                                detail=f"HTTP error: {content[:100]}"
                            )

                    # Read and parse response
                    try:
                        content = await response.text()
                        if not content.strip():
                            raise CommandError(
                                "ERROR_MISSING_EXPECTED_DATA",
                                self.user_locale,
                                ip=self.ip,
                                detail="Device returned empty response"
                            )
                        
                        json_response = json.loads(content)
                        
                        # Validate response structure
                        if not isinstance(json_response, dict):
                            raise CommandError(
                                "ERROR_INVALID_JSON",
                                self.user_locale,
                                ip=self.ip,
                                detail="Response is not a JSON object"
                            )
                            
                        # Check device response code if present
                        device_code = json_response.get("code")
                        if device_code is not None and device_code != RESPONSE_CODE_SUCCESS:
                            raise CommandError(
                                "ERROR_COMMAND_EXECUTION",
                                self.user_locale,
                                ip=self.ip,
                                detail=f"Device returned error code {device_code}"
                            )
                        
                        return json_response
                        
                    except json.JSONDecodeError as e:
                        raise CommandError(
                            "ERROR_INVALID_JSON",
                            self.user_locale,
                            ip=self.ip,
                            detail=f"Invalid JSON response: {e}"
                        )
                    except UnicodeDecodeError as e:
                        raise CommandError(
                            "ERROR_RESPONSE_DECODE",
                            self.user_locale,
                            ip=self.ip,
                            detail=f"Response encoding error: {e}"
                        )
                        
            except asyncio.TimeoutError as e:
                timeout_detail = f"HTTP timeout after {timeout}s (attempt {attempt + 1}/{retries + 1}) for URL: {url}"
                last_exception = MaxSmartConnectionError(
                    self.user_locale,
                    "ERROR_TIMEOUT_DETAIL",
                    ip=self.ip,
                    detail=timeout_detail
                )
                
            except aiohttp.ClientConnectionError as e:
                connection_detail = f"Connection failed: {type(e).__name__} - {str(e)} (attempt {attempt + 1}/{retries + 1})"
                last_exception = MaxSmartConnectionError(
                    self.user_locale,
                    "ERROR_CONNECTION_REFUSED", 
                    ip=self.ip,
                    detail=connection_detail
                )
                
            except aiohttp.ClientError as e:
                client_detail = f"HTTP client error: {type(e).__name__} - {str(e)} (attempt {attempt + 1}/{retries + 1})"
                last_exception = MaxSmartConnectionError(
                    self.user_locale,
                    "ERROR_CLIENT_ERROR",
                    ip=self.ip,
                    detail=client_detail
                )
                
            except OSError as e:
                # Network-level errors (DNS, routing, etc.)
                if "Network is unreachable" in str(e):
                    error_type = "ERROR_NETWORK_ISSUE"
                    detail = f"Network unreachable: {str(e)} (attempt {attempt + 1}/{retries + 1})"
                elif "Name or service not known" in str(e):
                    error_type = "ERROR_DNS_RESOLUTION"
                    detail = f"DNS resolution failed: {str(e)} (attempt {attempt + 1}/{retries + 1})"
                else:
                    error_type = "ERROR_SOCKET_ERROR"
                    detail = f"Socket error: {str(e)} (attempt {attempt + 1}/{retries + 1})"
                
                last_exception = MaxSmartConnectionError(
                    self.user_locale,
                    error_type,
                    ip=self.ip,
                    detail=detail
                )
                
            except (CommandError, MaxSmartConnectionError):
                # Re-raise our custom exceptions immediately (no retry)
                raise
                
            except Exception as e:
                # Unexpected errors - don't retry
                raise CommandError(
                    "ERROR_UNEXPECTED",
                    self.user_locale,
                    ip=self.ip,
                    detail=f"Unexpected error: {type(e).__name__}: {e}"
                )
            
            # If this wasn't the last attempt, wait before retrying
            if attempt < retries:
                delay = self.RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                await asyncio.sleep(delay)
        
        # All retries exhausted, raise the last exception
        if last_exception:
            raise last_exception
        else:
            # This should never happen, but just in case
            raise MaxSmartConnectionError(
                self.user_locale,
                "ERROR_NETWORK_ISSUE",
                ip=self.ip,
                detail=f"All {retries + 1} attempts failed without specific error"
            )
    
    async def _send_udp_v3_command(self, cmd, params=None, timeout=None):
        """
        Send a command to the device via UDP V3 protocol.
        
        :param cmd: HTTP command identifier (will be mapped to UDP V3)
        :param params: Additional parameters for the command
        :param timeout: Request timeout in seconds
        :return: Response from the device as JSON
        
        :raises CommandError: For command validation or execution errors
        :raises MaxSmartConnectionError: For network/connectivity issues
        """
        if timeout is None:
            timeout = self.UDP_V3_TIMEOUT
            
        # Map HTTP command to UDP V3 command
        if cmd not in self.HTTP_TO_UDP_V3_COMMANDS:
            raise CommandError(
                "ERROR_UNSUPPORTED_COMMAND",
                self.user_locale,
                ip=self.ip,
                detail=f"Command {cmd} not supported in UDP V3 protocol"
            )
        
        udp_v3_cmd = self.HTTP_TO_UDP_V3_COMMANDS[cmd]
        
        # Validate that we have the serial number for UDP V3
        if not hasattr(self, 'sn') or not self.sn:
            raise CommandError(
                "ERROR_MISSING_EXPECTED_DATA",
                self.user_locale,
                ip=self.ip,
                detail="Serial number required for UDP V3 commands"
            )
        
        # Build command payload
        payload = {
            "sn": self.sn,
            "cmd": udp_v3_cmd
        }
        
        # Add specific parameters based on command type
        if cmd == CMD_SET_PORT_STATE and params:
            # Port control command (HTTP 200 -> UDP V3 20)
            payload.update({
                "port": params.get("port", 0),
                "state": params.get("state", 0)
            })
        elif cmd == CMD_GET_DEVICE_DATA:
            # Data query command (HTTP 511 -> UDP V3 90) - no additional params needed
            pass
        
        # Format as V3{...} message
        message = f"V3{json.dumps(payload, separators=(',', ':'))}"
        
        # Send command with retry logic
        last_exception = None
        for attempt in range(self.UDP_V3_RETRIES):
            try:
                response = await self._send_udp_v3_message(message, timeout)
                
                # Validate response
                if not isinstance(response, dict):
                    raise CommandError(
                        "ERROR_INVALID_JSON",
                        self.user_locale,
                        ip=self.ip,
                        detail="Invalid response format from UDP V3 device"
                    )
                
                # Check response code
                code = response.get("code")
                if code == 200:
                    # Convert UDP V3 response to HTTP-like format for compatibility
                    return self._convert_udp_v3_response(response, udp_v3_cmd)
                elif code == 400:
                    raise CommandError(
                        "ERROR_COMMAND_EXECUTION",
                        self.user_locale,
                        ip=self.ip,
                        detail=f"Device rejected UDP V3 command {udp_v3_cmd}"
                    )
                else:
                    raise CommandError(
                        "ERROR_COMMAND_EXECUTION",
                        self.user_locale,
                        ip=self.ip,
                        detail=f"Unexpected response code: {code}"
                    )
                    
            except (CommandError, MaxSmartConnectionError):
                # Don't retry command or connection errors
                raise
            except Exception as e:
                last_exception = e
                if attempt < self.UDP_V3_RETRIES - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                    
        # All retries failed
        if last_exception:
            raise MaxSmartConnectionError(
                user_locale=self.user_locale,
                error_key="ERROR_NETWORK_ISSUE",
                ip=self.ip,
                detail=f"UDP V3 command failed after {self.UDP_V3_RETRIES} attempts: {last_exception}"
            )
    
    async def _send_udp_v3_message(self, message, timeout):
        """
        Send a single UDP V3 message and receive response.
        
        :param message: V3{...} formatted message
        :param timeout: Timeout in seconds
        :return: Parsed JSON response
        """
        loop = asyncio.get_event_loop()
        sock = None
        
        try:
            # Create UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(False)
            
            # Send message to device
            await loop.run_in_executor(
                None, sock.sendto, message.encode('utf-8'), (self.ip, UDP_PORT)
            )
            
            # Set timeout and wait for response
            sock.settimeout(timeout)
            
            # Receive response
            data, addr = await loop.run_in_executor(None, sock.recvfrom, 1024)
            
            # Parse JSON response
            response_text = data.decode('utf-8', errors='replace')
            response_json = json.loads(response_text)
            
            return response_json
            
        except socket.timeout:
            raise MaxSmartConnectionError(
                user_locale=self.user_locale,
                error_key="ERROR_TIMEOUT_DETAIL",
                ip=self.ip,
                detail=f"UDP V3 command timeout after {timeout}s"
            )
        except json.JSONDecodeError as e:
            raise CommandError(
                "ERROR_INVALID_JSON",
                self.user_locale,
                ip=self.ip,
                detail=f"Invalid JSON in UDP V3 response: {e}"
            )
        except OSError as e:
            raise MaxSmartConnectionError(
                user_locale=self.user_locale,
                error_key="ERROR_NETWORK_ISSUE",
                ip=self.ip,
                detail=f"UDP socket error: {e}"
            )
        finally:
            if sock:
                try:
                    sock.close()
                except:
                    pass
    
    def _convert_udp_v3_response(self, udp_response, udp_cmd):
        """
        Convert UDP V3 response format to HTTP-compatible format.
        
        :param udp_response: Raw UDP V3 response
        :param udp_cmd: UDP V3 command number
        :return: HTTP-compatible response
        """
        if udp_cmd == 20:  # Port control command
            # UDP V3 control commands return: {"response": 20, "code": 200}
            # Convert to HTTP-like format
            return {
                "code": udp_response.get("code", 200),
                "response": udp_response.get("response", udp_cmd)
            }
        
        elif udp_cmd == 90:  # Data query command
            # UDP V3 data response: {"response": 90, "code": 200, "data": {"watt": [...], "amp": [...], "switch": [...]}}
            # Convert to HTTP-like format with "data" wrapper
            data = udp_response.get("data", {})
            
            # Note: UDP V3 returns watt in milliwatts (integers), 
            # amp in milliamperes (integers), switch as 0/1 array
            return {
                "code": udp_response.get("code", 200),
                "response": udp_response.get("response", udp_cmd),
                "data": {
                    "watt": data.get("watt", []),      # Will be converted by _convert_watt_list()
                    "switch": data.get("switch", [])   # Direct use
                    # Note: amp data available but not used by current module
                }
            }
        
        else:
            # Unknown command, return as-is
            return udp_response