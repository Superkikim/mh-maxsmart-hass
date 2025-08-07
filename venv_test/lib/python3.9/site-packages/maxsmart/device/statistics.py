# maxsmart/device/statistics.py

from ..exceptions import StateError, CommandError, DeviceOperationError
from ..const import (
    CMD_GET_DEVICE_DATA,
    CMD_GET_STATISTICS,
    MAX_PORT_NUMBER,
    CURRENCY_SYMBOLS,
    STATISTICS_TIME_FRAME,
    UNSUPPORTED_COMMAND_MESSAGES,
)
from ..utils import get_user_message


class StatisticsMixin:
    """Mixin class providing statistics and power monitoring functionality."""

    async def get_statistics(self, port, stat_type):
        """
        Retrieve statistics for a specific port or all ports.
        
        Note: Only available on HTTP protocol devices.
        
        :param port: The port number (0 for all ports).
        :param stat_type: The type of statistics (0 = hourly, 1 = daily, 2 = monthly).
        :return: A dictionary containing statistics data.
        
        :raises CommandError: If device doesn't support statistics (UDP V3 devices)
        """
        # Check protocol support
        if hasattr(self, 'protocol') and self.protocol == 'udp_v3':
            error_msg = get_user_message(
                UNSUPPORTED_COMMAND_MESSAGES,
                "ERROR_UDP_V3_LIMITATION",
                self.user_locale,
                feature="statistics"
            )
            raise CommandError(
                "ERROR_UNSUPPORTED_COMMAND",
                self.user_locale,
                ip=self.ip,
                protocol=self.protocol,
                detail=error_msg
            )

        if not (0 <= port <= MAX_PORT_NUMBER):
            raise DeviceOperationError(
                self.user_locale
            )  # Raise with invalid parameters error

        if stat_type not in STATISTICS_TIME_FRAME.keys():
            raise CommandError(
                "ERROR_INVALID_PARAMETERS", self.user_locale
            )  # Raise with invalid parameters error

        try:
            response = await self._send_command(
                CMD_GET_STATISTICS, params={"type": stat_type}
            )

            # Validate the response structure
            if not isinstance(response, dict) or "data" not in response:
                raise CommandError("ERROR_INVALID_JSON", self.user_locale)

            data = response["data"]

            cost = float(data.get("cost", 0))
            currency = CURRENCY_SYMBOLS.get(
                data["money"], "$"
            )  # Use default $ if not found
            watt_data = data["watt"]

            # Extract date
            date_str = data["date"]
            date_parts = date_str.split("-")

            if stat_type == 0:  # hourly
                if len(date_parts) != 4:
                    raise ValueError(f"Invalid date format for hourly data: {date_str}")
                year, month, day, hour = map(int, date_parts)
            elif stat_type == 1:  # daily
                if len(date_parts) != 3:
                    raise ValueError(f"Invalid date format for daily data: {date_str}")
                year, month, day = map(int, date_parts)
                hour = 0  # Set hour to 0 for daily stats
            elif stat_type == 2:  # monthly
                if len(date_parts) != 2:
                    raise ValueError(
                        f"Invalid date format for monthly data: {date_str}"
                    )
                year, month = map(int, date_parts)
                day = 1  # Set day to 1 for monthly stats
                hour = 0  # Set hour to 0 for monthly stats
            else:
                raise ValueError(f"Invalid stat_type: {stat_type}")

            # If port is 0, sum the watt data across all ports with conversion
            if port == 0:
                summed_watt = [
                    sum(self._convert_watt(value) for value in port_data)
                    for port_data in zip(*watt_data)
                ]
            else:  # For specific port
                if not watt_data or (port - 1) >= len(watt_data):
                    raise StateError("ERROR_MISSING_EXPECTED_DATA", self.user_locale)
                summed_watt = [self._convert_watt(value) for value in watt_data[port - 1]]

            # Construct result
            result = {
                "cost": cost,
                "currency": currency,
                "type": STATISTICS_TIME_FRAME[stat_type],
                "year": year,
                "month": month,
                "day": day,
                "hour": hour,
                "watt": summed_watt,  # List of wattage for the given port or all ports summed
            }
            return result

        except CommandError as e:
            raise CommandError(
                "ERROR_COMMAND_EXECUTION", self.user_locale, detail=str(e)
            )
        except StateError as e:
            raise StateError(str(e))
        except Exception as e:
            import traceback

            traceback.print_exc()
            raise StateError(f"Unexpected error: {str(e)}")

    async def get_power_data(self, port):
        """
        Retrieve real-time power consumption data for a specific port.
        
        Works with both HTTP and UDP V3 protocols.
        
        :param port: The port number (1-6).
        :return: Dictionary containing power data.
        """
        try:
            response = await self._send_command(CMD_GET_DEVICE_DATA, params=None)
            data = response.get("data", {})
            watt = data.get("watt", [])
            
            if not watt or port < 1 or port > len(watt):
                raise StateError(
                    f"No watt data received or invalid port number: {port}"
                )
            
            raw_watt = watt[port - 1]
            converted_watt = self._convert_watt(raw_watt)
            
            return {"watt": converted_watt}
            
        except CommandError as e:
            raise CommandError(f"Failed to get power data for port {port}: {str(e)}")