# maxsmart/discovery.py

import asyncio
import socket
import json
import datetime
import os
import logging

from .const import (
    DEFAULT_TARGET_IP,
    UDP_PORT,
    UDP_TIMEOUT,
    DISCOVERY_MESSAGE,
    CMD_GET_DEVICE_IDS
)

from .exceptions import (
    DiscoveryError,
    ConnectionError,
    UdpTimeoutInfo
)


class MaxSmartDiscovery:
    """MaxSmart device discovery with protocol detection and simplified hardware enhancement."""
    
    # Discovery configuration
    DEFAULT_DISCOVERY_TIMEOUT = 2.0  # seconds - devices respond very quickly
    MAX_DISCOVERY_ATTEMPTS = 3
    SOCKET_RETRY_DELAY = 0.5  # seconds
    
    @staticmethod
    async def discover_maxsmart(ip=None, user_locale="en", timeout=None, max_attempts=None, enhance_with_hardware_ids=True):
        """
        Discover MaxSmart devices with protocol detection and optional hardware enhancement.
        
        :param ip: Specific IP to query (None for broadcast)
        :param user_locale: User locale for error messages
        :param timeout: Discovery timeout in seconds
        :param max_attempts: Maximum discovery attempts
        :param enhance_with_hardware_ids: Whether to enhance with hardware IDs
        :return: List of discovered devices with protocol information
        
        :raises DiscoveryError: For discovery-related errors
        :raises ConnectionError: For network connectivity issues
        """
        # Use default values if not specified
        if timeout is None:
            timeout = float(os.getenv("UDP_TIMEOUT", MaxSmartDiscovery.DEFAULT_DISCOVERY_TIMEOUT))
        if max_attempts is None:
            max_attempts = MaxSmartDiscovery.MAX_DISCOVERY_ATTEMPTS
            
        target_ip = ip if ip else DEFAULT_TARGET_IP
        is_broadcast = (ip is None or ip == DEFAULT_TARGET_IP)
        
        # Validate IP format for unicast
        if ip and ip != DEFAULT_TARGET_IP:
            try:
                socket.inet_aton(ip)
            except socket.error:
                raise DiscoveryError(
                    "ERROR_INVALID_IP_FORMAT",
                    user_locale,
                    ip=ip,
                    detail=f"Invalid IP address format: {ip}"
                )
        
        # Prepare discovery message
        current_time = datetime.datetime.now().strftime('%Y-%m-%d,%H:%M:%S')
        message = DISCOVERY_MESSAGE.format(datetime=current_time)
        
        maxsmart_devices = []
        last_exception = None
        
        # Discovery attempt loop
        for attempt in range(max_attempts):
            try:
                devices = await MaxSmartDiscovery._single_discovery_attempt(
                    target_ip, message, timeout, user_locale, is_broadcast
                )
                
                if devices:
                    maxsmart_devices.extend(devices)
                    
                # For unicast, one successful response is enough
                if not is_broadcast and devices:
                    break
                    
                # For broadcast, continue collecting responses
                if is_broadcast and attempt == 0:
                    # First attempt successful, but continue for more devices
                    continue
                    
            except (ConnectionError, DiscoveryError) as e:
                last_exception = e
                logging.debug(f"Discovery attempt {attempt + 1} failed: {e}")
                
                # For unicast failures, wait before retry
                if not is_broadcast and attempt < max_attempts - 1:
                    await asyncio.sleep(MaxSmartDiscovery.SOCKET_RETRY_DELAY * (attempt + 1))
                    
            except Exception as e:
                # Unexpected errors
                raise DiscoveryError(
                    "ERROR_DISCOVERY_FAILED",
                    user_locale,
                    detail=f"Unexpected discovery error: {type(e).__name__}: {e}"
                )
        
        # Remove duplicates based on IP address
        seen_ips = set()
        unique_devices = []
        for device in maxsmart_devices:
            if device["ip"] not in seen_ips:
                seen_ips.add(device["ip"])
                unique_devices.append(device)
        
        # Always add protocol detection
        if unique_devices:
            unique_devices = await MaxSmartDiscovery._add_protocol_detection(
                unique_devices, user_locale
            )
        
        # Optional: enhance with essential hardware identifiers (only for HTTP devices)
        if enhance_with_hardware_ids and unique_devices:
            unique_devices = await MaxSmartDiscovery._enhance_with_essential_ids(
                unique_devices, user_locale
            )
        
        # Log discovery results
        if unique_devices:
            logging.info(f"Found {len(unique_devices)} MaxSmart device(s)")
            return unique_devices
        else:
            # No devices found after all attempts
            if last_exception:
                raise last_exception
            else:
                # Timeout without errors - this is normal for broadcast discovery
                if is_broadcast:
                    UdpTimeoutInfo(user_locale)  # Log timeout info
                    return []  # Return empty list for broadcast timeout
                else:
                    raise DiscoveryError("ERROR_NO_DEVICES_FOUND", user_locale)
    
    @staticmethod
    async def _single_discovery_attempt(target_ip, message, timeout, user_locale, is_broadcast):
        """
        Perform a single discovery attempt with proper error handling.
        
        :param target_ip: Target IP address
        :param message: Discovery message to send
        :param timeout: Timeout for this attempt
        :param user_locale: User locale for error messages
        :param is_broadcast: Whether this is a broadcast discovery
        :return: List of discovered devices in this attempt
        """
        loop = asyncio.get_event_loop()
        sock = None
        devices = []
        
        try:
            # Create and configure socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            if is_broadcast:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                
            sock.setblocking(False)
            
            # Bind to any available port
            try:
                sock.bind(('', 0))
            except OSError as e:
                raise ConnectionError(
                    user_locale=user_locale,
                    error_key="ERROR_NETWORK_ISSUE",
                    ip=target_ip,
                    detail=f"Failed to bind socket: {e}"
                )
            
            # Send discovery message
            try:
                await loop.run_in_executor(
                    None, sock.sendto, message.encode('utf-8'), (target_ip, UDP_PORT)
                )
            except OSError as e:
                if "Network is unreachable" in str(e):
                    raise ConnectionError(
                        user_locale=user_locale,
                        error_key="ERROR_NETWORK_ISSUE",
                        ip=target_ip,
                        detail="Network unreachable - check network connectivity"
                    )
                elif "No route to host" in str(e):
                    raise ConnectionError(
                        user_locale=user_locale,
                        error_key="ERROR_NETWORK_ISSUE", 
                        ip=target_ip,
                        detail=f"No route to host {target_ip}"
                    )
                else:
                    raise ConnectionError(
                        user_locale=user_locale,
                        error_key="ERROR_NETWORK_ISSUE",
                        ip=target_ip,
                        detail=f"Failed to send discovery message: {e}"
                    )
            
            # Set socket timeout for receiving
            sock.settimeout(timeout)
            
            # Collect responses
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                try:
                    # Receive response
                    data, addr = await loop.run_in_executor(None, sock.recvfrom, 1024)
                    
                    try:
                        # Decode and parse response
                        raw_result = data.decode("utf-8", errors="replace")
                        json_data = json.loads(raw_result)
                        device_data = json_data.get("data", {})
                        
                        if device_data:
                            # Extract device information (simplified format)
                            device = {
                                "sn": device_data.get("sn", ""),
                                "name": device_data.get("name", ""),
                                "pname": device_data.get("pname", []),
                                "ip": addr[0],
                                "ver": device_data.get("ver", ""),
                            }
                            devices.append(device)
                            
                            # For unicast, one response is usually enough
                            if not is_broadcast:
                                break
                                
                    except json.JSONDecodeError as e:
                        logging.debug(f"Received invalid JSON from {addr[0]}: {e}")
                        continue
                    except UnicodeDecodeError as e:
                        logging.debug(f"Received invalid UTF-8 from {addr[0]}: {e}")
                        continue
                        
                except socket.timeout:
                    # Normal timeout - stop collecting responses
                    break
                except OSError as e:
                    # Socket errors during receive
                    if "Resource temporarily unavailable" in str(e):
                        # Normal case when no more data available
                        break
                    else:
                        logging.debug(f"Socket error during receive: {e}")
                        break
                        
        except Exception as e:
            # Handle any other unexpected errors
            raise DiscoveryError(
                "ERROR_DISCOVERY_FAILED",
                user_locale,
                detail=f"Discovery attempt failed: {type(e).__name__}: {e}"
            )
        finally:
            # Always close the socket
            if sock:
                try:
                    sock.close()
                except:
                    pass  # Ignore close errors
        
        return devices

    @staticmethod
    async def _add_protocol_detection(devices, user_locale):
        """
        Add protocol detection to device list.
        
        :param devices: List of devices from UDP discovery
        :param user_locale: User locale for error messages
        :return: Device list with 'protocol' field added
        """
        enhanced_devices = []
        
        for device in devices:
            enhanced_device = device.copy()
            ip = device["ip"]
            sn = device.get("sn", "")
            
            try:
                # Detect protocol for this device
                protocol = await MaxSmartDiscovery._detect_device_protocol(ip, sn, user_locale)
                enhanced_device["protocol"] = protocol
                
                logging.debug(f"Device {ip} detected protocol: {protocol}")
                
            except Exception as e:
                # Protocol detection failed, default to 'unknown'
                logging.debug(f"Protocol detection failed for {ip}: {e}")
                enhanced_device["protocol"] = "unknown"
                
            enhanced_devices.append(enhanced_device)
            
        return enhanced_devices
    
    @staticmethod
    async def _detect_device_protocol(ip, sn, user_locale):
        """
        Detect which protocol a device supports by testing HTTP first, then UDP V3.
        
        :param ip: Device IP address
        :param sn: Device serial number (needed for UDP V3 test)
        :param user_locale: User locale for error messages
        :return: 'http', 'udp_v3', or 'unknown'
        """
        # Test HTTP protocol first (more features, preferred)
        if await MaxSmartDiscovery._test_http_protocol(ip):
            return 'http'
        
        # Test UDP V3 protocol if HTTP fails
        if sn and await MaxSmartDiscovery._test_udp_v3_protocol(ip, sn):
            return 'udp_v3'
        
        # Neither protocol works
        return 'unknown'
    
    @staticmethod
    async def _test_http_protocol(ip):
        """
        Quick test if device responds to HTTP commands.
        
        :param ip: Device IP address
        :return: True if HTTP works, False otherwise
        """
        try:
            import aiohttp
            
            # Quick HTTP test with cmd=511 (get device data)
            url = f"http://{ip}/?cmd=511"
            timeout = aiohttp.ClientTimeout(total=3.0)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.text()
                        # Basic validation - should be JSON with data
                        try:
                            json_data = json.loads(content)
                            return "data" in json_data
                        except json.JSONDecodeError:
                            return False
                    else:
                        return False
                        
        except Exception as e:
            logging.debug(f"HTTP protocol test failed for {ip}: {e}")
            return False
    
    @staticmethod
    async def _test_udp_v3_protocol(ip, sn):
        """
        Quick test if device responds to UDP V3 commands.
        
        :param ip: Device IP address
        :param sn: Device serial number
        :return: True if UDP V3 works, False otherwise
        """
        try:
            # Quick UDP V3 test with cmd=90 (get device data)
            payload = {"sn": sn, "cmd": 90}
            message = f"V3{json.dumps(payload, separators=(',', ':'))}"
            
            loop = asyncio.get_event_loop()
            sock = None
            
            try:
                # Create UDP socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setblocking(False)
                
                # Send UDP V3 message
                await loop.run_in_executor(
                    None, sock.sendto, message.encode('utf-8'), (ip, UDP_PORT)
                )
                
                # Set timeout and wait for response
                sock.settimeout(2.0)
                
                # Receive response
                data, addr = await loop.run_in_executor(None, sock.recvfrom, 1024)
                
                # Parse response
                response_text = data.decode('utf-8', errors='replace')
                response_json = json.loads(response_text)
                
                # Check if valid UDP V3 response
                return (response_json.get("response") == 90 and 
                        response_json.get("code") == 200 and
                        "data" in response_json)
                        
            except Exception as e:
                logging.debug(f"UDP V3 socket error for {ip}: {e}")
                return False
            finally:
                if sock:
                    try:
                        sock.close()
                    except:
                        pass
                        
        except Exception as e:
            logging.debug(f"UDP V3 protocol test failed for {ip}: {e}")
            return False

    @staticmethod
    async def _enhance_with_essential_ids(devices, user_locale):
        """
        Enhance device list with essential identifiers (only for HTTP devices).
        
        :param devices: List of devices from UDP discovery with protocol info
        :param user_locale: User locale for error messages
        :return: Enhanced device list with essential IDs
        """
        enhanced_devices = []
        
        # Import here to avoid circular imports
        from .device import MaxSmartDevice
        
        for device in devices:
            enhanced_device = device.copy()
            ip = device["ip"]
            protocol = device.get("protocol", "unknown")
            
            # Only enhance HTTP devices with hardware IDs
            if protocol == "http":
                try:
                    # Create temporary device instance to fetch essential IDs
                    temp_device = MaxSmartDevice(ip, protocol="http")
                    temp_device._is_temp_device = True  # Mark as temp to avoid circular calls
                    await temp_device.initialize_device()
                    
                    # Get essential identifiers
                    try:
                        hw_ids = await temp_device.get_device_identifiers()
                        enhanced_device["cpuid"] = hw_ids.get("cpuid", "")
                        enhanced_device["server"] = hw_ids.get("server", "")
                        
                        logging.debug(f"Enhanced HTTP device {ip} with CPU ID: {hw_ids.get('cpuid', 'None')[:8]}...")
                        
                    except Exception as e:
                        # Hardware ID fetch failed, use device as-is
                        logging.debug(f"Failed to get hardware IDs for {ip}: {e}")
                        enhanced_device["cpuid"] = ""
                        enhanced_device["server"] = ""
                    
                    # Get MAC address via ARP
                    try:
                        mac_address = await temp_device.get_mac_address_via_arp()
                        enhanced_device["mac"] = mac_address or ""
                        
                        logging.debug(f"MAC address for {ip}: {mac_address or 'Not found'}")
                        
                    except Exception as e:
                        logging.debug(f"Failed to get MAC address for {ip}: {e}")
                        enhanced_device["mac"] = ""
                        
                except Exception as e:
                    # Device initialization failed, use device as-is with empty fields
                    logging.debug(f"Failed to initialize HTTP device {ip} for enhancement: {e}")
                    enhanced_device["cpuid"] = ""
                    enhanced_device["server"] = ""
                    enhanced_device["mac"] = ""
                    
                finally:
                    # Always cleanup temp device
                    try:
                        if 'temp_device' in locals():
                            await temp_device.close()
                    except:
                        pass
            
            else:
                # UDP V3 or unknown devices - don't enhance with hardware IDs
                enhanced_device["cpuid"] = ""
                enhanced_device["server"] = ""
                enhanced_device["mac"] = ""
                
                logging.debug(f"Skipping hardware ID enhancement for {protocol} device {ip}")
                    
            enhanced_devices.append(enhanced_device)
            
        return enhanced_devices