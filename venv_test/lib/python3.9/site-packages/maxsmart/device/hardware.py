# maxsmart/device/hardware.py

from ..exceptions import CommandError, StateError
from ..const import CMD_GET_DEVICE_IDS, UNSUPPORTED_COMMAND_MESSAGES
from ..utils import get_mac_address_from_ip, get_user_message


class HardwareMixin:
    """Mixin class providing hardware identification functionality."""

    async def get_device_identifiers(self):
        """
        Retrieve essential hardware identifiers from the device.
        
        Note: Only available on HTTP protocol devices.
        
        Returns:
            dict: Dictionary containing essential identifiers
                  Format: {
                      "cpuid": "XXXXXXXXXXXXXXXX",       # CPU unique identifier
                      "server": "server.domain"          # Cloud server address
                  }
        
        Raises:
            CommandError: If device doesn't support hardware ID queries (UDP V3 devices) or command fails
            StateError: If device response is invalid
        """
        # Check protocol support
        if hasattr(self, 'protocol') and self.protocol == 'udp_v3':
            error_msg = get_user_message(
                UNSUPPORTED_COMMAND_MESSAGES,
                "ERROR_UDP_V3_LIMITATION",
                self.user_locale,
                feature="hardware identifiers"
            )
            raise CommandError(
                "ERROR_UNSUPPORTED_COMMAND",
                self.user_locale,
                ip=self.ip,
                protocol=self.protocol,
                detail=error_msg
            )
        
        try:
            response = await self._send_command(CMD_GET_DEVICE_IDS)
            
            # Validate response structure
            if not isinstance(response, dict) or "data" not in response:
                raise CommandError(
                    "ERROR_INVALID_JSON",
                    self.user_locale,
                    ip=self.ip,
                    detail="Received invalid data structure from device for command 124.",
                )

            # Extract hardware identifiers
            data = response["data"]
            
            # Only get essential fields from command 124
            identifiers = {
                "cpuid": data.get("cpuid", ""), 
                "server": data.get("server", "")
            }
            
            # Validate that we got at least CPU ID
            if not identifiers["cpuid"]:
                raise CommandError(
                    "ERROR_MISSING_EXPECTED_DATA", 
                    self.user_locale,
                    ip=self.ip,
                    detail="No CPU ID returned by device"
                )

            return identifiers

        except CommandError:
            raise  # Re-raise command errors as-is
        except Exception as e:
            raise StateError(
                "ERROR_UNEXPECTED", 
                self.user_locale, 
                ip=self.ip,
                detail=f"Unexpected error getting hardware identifiers: {str(e)}"
            )

    async def get_mac_address_via_arp(self):
        """
        Get MAC address from system ARP table.
        
        Works with both HTTP and UDP V3 protocols (uses system ARP, not device commands).
        
        Returns:
            str or None: MAC address or None if not found
        """
        return get_mac_address_from_ip(self.ip)