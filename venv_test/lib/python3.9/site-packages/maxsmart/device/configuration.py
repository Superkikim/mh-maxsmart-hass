# maxsmart/device/configuration.py

from ..exceptions import (
    StateError,
    CommandError,
    FirmwareError,
    DeviceOperationError,
    DiscoveryError,
    ConnectionError,
)
from ..const import (
    CMD_SET_PORT_NAME,
    MAX_PORT_NUMBER,
    MAX_PORT_NAME_LENGTH,
    IN_DEVICE_NAME_VERSION,
    RESPONSE_CODE_SUCCESS,
    UDP_PORT,
    DISCOVERY_MESSAGE,
    UNSUPPORTED_COMMAND_MESSAGES,
)
from ..utils import get_user_message


class ConfigurationMixin:
    """Mixin class providing device configuration functionality (port names, etc.)."""

    async def retrieve_port_names(self):
        """
        Retrieve current port names by sending a direct UDP request to the device.
        
        Note: Works with both protocols, but UDP V3 devices may not have configurable names.
        """
        if not self.ip:
            raise StateError(
                "ERROR_MISSING_EXPECTED_DATA", self.user_locale
            )

        try:
            # Direct UDP unicast to get port names without using discovery
            device_data = await self._get_port_names_via_udp()
            
            if not device_data:
                raise DiscoveryError(
                    "ERROR_NO_DEVICES_FOUND", self.user_locale
                )

            self.strip_name = device_data.get("name", self.strip_name)  # Name for port 0
            self.port_names = device_data.get("pname", self.port_names)  # Names for ports 1 to 6

            # Combine in a dictionary
            port_mapping = {
                "Port 0": self.strip_name,
            }
            for i in range(1, 7):
                port_mapping[f"Port {i}"] = (
                    self.port_names[i - 1]
                    if i - 1 < len(self.port_names)
                    else f"Port {i}"
                )

            return port_mapping

        except ConnectionError:
            raise ConnectionError(
                "ERROR_NETWORK_ISSUE", self.user_locale
            )
        except DiscoveryError:
            raise DiscoveryError(
                "ERROR_NO_DEVICES_FOUND", self.user_locale
            )
        except Exception as e:
            raise StateError(
                "ERROR_UNEXPECTED", self.user_locale, detail=str(e)
            )

    async def _get_port_names_via_udp(self):
        """Get port names via direct UDP unicast to device IP."""
        import asyncio
        import socket
        import json
        from ..const import UDP_PORT, DISCOVERY_MESSAGE
        
        sock = None
        try:
            # Create UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Send discovery message directly to device IP
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, sock.sendto, DISCOVERY_MESSAGE.encode('utf-8'), (self.ip, UDP_PORT)
            )
            
            # Set timeout and wait for response
            sock.settimeout(2.0)
            
            # Receive response
            data, addr = await loop.run_in_executor(None, sock.recvfrom, 1024)
            
            # Parse response
            raw_result = data.decode("utf-8", errors="replace")
            json_data = json.loads(raw_result)
            device_data = json_data.get("data", {})
            
            return device_data
            
        except socket.timeout:
            raise ConnectionError("ERROR_NETWORK_ISSUE", self.user_locale)
        except Exception as e:
            raise StateError("ERROR_UNEXPECTED", self.user_locale, detail=str(e))
        finally:
            if sock:
                try:
                    sock.close()
                except:
                    pass

    async def change_port_name(self, port, new_name):
        """
        Change the name of a specific port asynchronously.
        
        Note: Only available on HTTP protocol devices with firmware v1.30.

        Args:
            port (int): The port number (0-6) to change the name for.
            new_name (str): The new name for the port (max 21 characters).

        Raises:
            CommandError: If device doesn't support port naming (UDP V3 devices)
            StateError: If the port number is invalid, the new name is empty, or the new name is too long.
            FirmwareError: If the device firmware does not support in-device port renaming.
        """
        # Check protocol support first
        if hasattr(self, 'protocol') and self.protocol == 'udp_v3':
            error_msg = get_user_message(
                UNSUPPORTED_COMMAND_MESSAGES,
                "ERROR_UDP_V3_LIMITATION",
                self.user_locale,
                feature="port naming"
            )
            raise CommandError(
                "ERROR_UNSUPPORTED_COMMAND",
                self.user_locale,
                ip=self.ip,
                protocol=self.protocol,
                detail=error_msg
            )
        
        # Check firmware version for in-device renaming support
        if self.version != IN_DEVICE_NAME_VERSION:
            raise FirmwareError(
                self.ip, self.version, self.user_locale, IN_DEVICE_NAME_VERSION
            )

        if not 0 <= port <= MAX_PORT_NUMBER:
            raise DeviceOperationError(
                self.user_locale
            )  # Raise with invalid parameters error

        if not new_name or new_name.strip() == "":
            raise StateError(
                "ERROR_INVALID_PARAMETERS", self.user_locale
            )  # Invalid parameters error

        if len(new_name) > MAX_PORT_NAME_LENGTH:
            raise StateError("ERROR_UNEXPECTED_STATE", self.user_locale)  # Length error

        try:
            params = {"port": port, "name": new_name}
            # Correctly call the send command method
            response = await self._send_command(
                CMD_SET_PORT_NAME, params
            )  # Updated method call

            # Check if the command was successful
            if response.get("code") == RESPONSE_CODE_SUCCESS:
                if port == 0:
                    self.strip_name = new_name  # Update the strip name
                else:
                    self.port_names[port - 1] = new_name  # Update the port name

                return True  # Successfully changed the name
            else:
                raise CommandError(
                    "ERROR_COMMAND_EXECUTION", self.user_locale
                )  # Handle command execution error

        except CommandError as e:
            raise CommandError(
                "ERROR_COMMAND_EXECUTION", self.user_locale
            )  # Handle command execution error
        except Exception as e:
            raise StateError(self.user_locale)  # Provide a more generalized state error