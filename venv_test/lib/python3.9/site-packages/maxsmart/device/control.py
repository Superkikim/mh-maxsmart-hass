# maxsmart/device/control.py

from ..exceptions import StateError, CommandError, DeviceOperationError
from ..const import CMD_SET_PORT_STATE, CMD_GET_DEVICE_DATA


class ControlMixin:
    """Mixin class providing device control functionality (turn on/off, state checking)."""

    async def turn_on(self, port):
        """Turn on a specific port."""
        params = {"port": port, "state": 1}
        await self._send_command(CMD_SET_PORT_STATE, params)

        # Verify the state after turning on
        attempts = 0
        while attempts < 3:
            try:
                await self._verify_state(port, 1)  # Check if the port is ON
                return  # Exit after successful operation
            except StateError:
                attempts += 1

        # Raise an error indicating the state is unexpected after 3 attempts
        raise StateError(
            "ERROR_UNEXPECTED_STATE", self.user_locale
        )  # Localized error for unexpected state

    async def turn_off(self, port):
        """Turn off a specific port."""
        params = {"port": port, "state": 0}
        await self._send_command(CMD_SET_PORT_STATE, params)

        # Verify the state after turning off
        attempts = 0
        while attempts < 3:
            try:
                await self._verify_state(port, 0)  # Check if the port is OFF
                return  # Exit after successful operation
            except StateError:
                attempts += 1

        # Raise an error indicating the state is unexpected after 3 attempts
        raise StateError(
            "ERROR_UNEXPECTED_STATE", self.user_locale
        )  # Localized error for unexpected state

    async def get_data(self):
        """
        Retrieve device data, including wattage and switch states.
        :return: Dictionary containing switch state and wattage data.
        """
        try:
            response = await self._send_command(CMD_GET_DEVICE_DATA)

            # Validate the response structure
            if (
                not isinstance(response, dict)
                or "data" not in response
                or "switch" not in response["data"]
            ):
                raise CommandError(
                    "ERROR_INVALID_JSON",
                    self.user_locale,
                    detail="Received invalid data structure from device.",
                )

            # Extract necessary information
            data = response["data"]
            switch_states = data.get("switch")
            wattages = data.get("watt")

            if switch_states is None or wattages is None:
                raise CommandError("ERROR_MISSING_EXPECTED_DATA", self.user_locale)

            # Convert wattage values using centralized conversion
            watt_value = self._convert_watt_list(wattages)

            # Return the structured data
            return {"switch": switch_states, "watt": watt_value}

        except CommandError:
            raise CommandError(
                "ERROR_COMMAND_EXECUTION", self.user_locale
            )  # Use standardized error message
        except Exception as e:
            raise CommandError(
                "ERROR_UNEXPECTED", self.user_locale, detail=str(e)
            )  # Handle unexpected errors

    async def check_state(self, port=None):
        """Check the state of a specific port or all ports."""
        try:
            data = await self.get_data()

            # Validate the response structure
            if "switch" not in data:
                raise StateError(self.user_locale)

            # If a specific port number is provided, return its state
            if port is not None:
                # Validate the port number
                if not 1 <= port <= 6:
                    raise DeviceOperationError(self.user_locale)

                return data["switch"][port - 1]  # Return state for the specified port

            # Return the list of states for all ports
            return data["switch"]

        except CommandError as e:
            raise CommandError(
                "ERROR_COMMAND_EXECUTION", self.user_locale, detail=str(e)
            )
        except Exception as e:
            raise StateError(self.user_locale)  # Simplified error handling

    async def _verify_state(self, port, expected_state):
        """
        Verify that a specific port or all ports are in the expected state.

        :param port: Port number (0 to 6). If 0, verify state for all ports.
        :param expected_state: The state expected (1 for ON, 0 for OFF).
        """
        try:
            if port == 0:
                # Check if all ports have the same expected state
                all_states = await self.check_state()  # Fetch all port states
                for state in all_states:
                    if state != expected_state:
                        raise StateError(
                            self.user_locale
                        )  # Raise if any port is not as expected
            else:
                # Validate a specific port only
                if not 1 <= port <= 6:
                    raise DeviceOperationError(self.user_locale)

                current_state = await self.check_state(
                    port
                )  # Get the specific port state
                if current_state != expected_state:
                    raise StateError(
                        self.user_locale
                    )  # Raise if the specific port is not as expected

        except CommandError as e:
            raise CommandError(
                "ERROR_COMMAND_EXECUTION", self.user_locale, detail=str(e)
            )
        except Exception as e:
            raise StateError(self.user_locale)  # Handle unexpected errors