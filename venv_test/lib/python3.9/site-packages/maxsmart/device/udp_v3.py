# maxsmart/device/udp_v3.py

import socket
import json
import asyncio
import logging
from ..exceptions import CommandError

class UdpV3Mixin:
    """Support for UDP V3 API commands (cmd 20, 90)"""
    
    async def _send_udp_v3_command(self, command_dict, timeout=5.0):
        """
        Send UDP V3 command and return response.
        
        Args:
            command_dict: Dict with 'sn', 'cmd', and other parameters
            timeout: Response timeout in seconds
            
        Returns:
            Dict: JSON response or raises CommandError
        """
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('', 0))
            sock.settimeout(timeout)
            
            message = f'V3{json.dumps(command_dict, separators=(",", ":"))}'
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, sock.sendto, message.encode('utf-8'), (self.ip, 8888)
            )
            
            data, addr = await loop.run_in_executor(None, sock.recvfrom, 1024)
            response = json.loads(data.decode('utf-8'))
            
            logging.debug(f"UDP V3 command to {self.ip}: {message}")
            return response
            
        except Exception as e:
            logging.error(f"UDP V3 command failed for {self.ip}: {e}")
            raise CommandError(
                "ERROR_COMMAND_EXECUTION",
                self.user_locale,
                ip=self.ip,
                detail=f"UDP V3 command failed: {e}"
            )
        finally:
            if sock:
                sock.close()
    
    async def turn_on_v3(self, port):
        """Turn on port via UDP V3 cmd=20"""
        command = {
            "sn": self.sn,
            "cmd": 20,
            "port": port,
            "state": 1
        }
        
        response = await self._send_udp_v3_command(command)
        
        if response and response.get('code') == 200:
            return True
        else:
            raise CommandError(
                "ERROR_COMMAND_EXECUTION",
                self.user_locale,
                ip=self.ip,
                detail=f"Turn ON failed: {response}"
            )
    
    async def turn_off_v3(self, port):
        """Turn off port via UDP V3 cmd=20"""
        command = {
            "sn": self.sn,
            "cmd": 20,
            "port": port,
            "state": 0
        }
        
        response = await self._send_udp_v3_command(command)
        
        if response and response.get('code') == 200:
            return True
        else:
            raise CommandError(
                "ERROR_COMMAND_EXECUTION",
                self.user_locale,
                ip=self.ip,
                detail=f"Turn OFF failed: {response}"
            )
    
    async def get_data_v3(self):
        """Get device status and consumption via UDP V3 cmd=90"""
        command = {
            "sn": self.sn,
            "cmd": 90
        }
        
        response = await self._send_udp_v3_command(command)
        
        if response and response.get('code') == 200:
            data = response.get('data', {})
            raw_watt = data.get('watt', [])
            
            # Use existing conversion logic: int = milliwatts, float = watts
            converted_watt = self._convert_watt_list(raw_watt)
            
            return {
                'switch': data.get('switch', []),
                'watt': converted_watt
            }
        else:
            raise CommandError(
                "ERROR_COMMAND_EXECUTION",
                self.user_locale,
                ip=self.ip,
                detail=f"Get data failed: {response}"
            )