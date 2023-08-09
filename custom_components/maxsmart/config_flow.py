import logging
import ipaddress
from homeassistant import config_entries, exceptions
from homeassistant.const import CONF_IP_ADDRESS
import voluptuous as vol
from maxsmart import MaxSmartDiscovery, MaxSmartDevice

from .const import (
    DOMAIN,
    CONF_DEVICE_NAME,
    CONF_PORT1_NAME,
    CONF_PORT2_NAME,
    CONF_PORT3_NAME,
    CONF_PORT4_NAME,
    CONF_PORT5_NAME,
    CONF_PORT6_NAME,
    CONF_ADD_MORE,
)

_LOGGER = logging.getLogger(__name__)

# Schema for devices with version 2.11

DATA_SCHEMA_MULTI_PORTS = vol.Schema(
    {
        vol.Required(CONF_DEVICE_NAME, description="Device Name"): vol.All(
            str, vol.Length(min=1)
        ),
        vol.Required(CONF_PORT1_NAME, description="Port 1 Name"): vol.All(
            str, vol.Length(min=1)
        ),
        vol.Required(CONF_PORT2_NAME, description="Port 2 Name"): vol.All(
            str, vol.Length(min=1)
        ),
        vol.Required(CONF_PORT3_NAME, description="Port 3 Name"): vol.All(
            str, vol.Length(min=1)
        ),
        vol.Required(CONF_PORT4_NAME, description="Port 4 Name"): vol.All(
            str, vol.Length(min=1)
        ),
        vol.Required(CONF_PORT5_NAME, description="Port 5 Name"): vol.All(
            str, vol.Length(min=1)
        ),
        vol.Required(CONF_PORT6_NAME, description="Port 6 Name"): vol.All(
            str, vol.Length(min=1)
        ),
    }
)

# Schema for manual device addition
DATA_SCHEMA_MANUAL = vol.Schema(
    {
        vol.Required(CONF_IP_ADDRESS): str
    }
)

# Schema for overwriting existing device
DATA_SCHEMA_OVERWRITE = vol.Schema(
    {
        vol.Required("overwrite", description="Overwrite existing entry?"): vol.In(
            ["Yes", "No"]
        ),
    }
)

DATA_SCHEMA_ADD_MORE = vol.Schema(
    {
        vol.Required(CONF_ADD_MORE, description="Add more devices?"): vol.In(
            ["Yes", "No"]
        ),
    }
)


def is_valid_ipv4(ip):
    try:
        # Attempt to create an IPv4Address object from the input string
        ipv4_address = ipaddress.IPv4Address(ip)
        return True
    except ipaddress.AddressValueError:
        # Raised when the input string is not a valid IPv4 address
        return False


async def async_get_number_of_ports(hass, ip_address):
    """Get the number of ports for the device with the given IP address."""
    _LOGGER.debug("Checking number of ports")
    device = MaxSmartDevice(ip_address)
    state = await hass.async_add_executor_job(device.check_state)
    # Logic to determine the number of ports from the state
    # (replace with the appropriate logic for your use case)
    return len(state)


class MaxSmartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """MaxSmart Config Flow"""

    VERSION = 1

    def __init__(self):
        super().__init__()
        self._errors = {}
        self.devices = []  # The list of devices
        self.device_data = None  # A single device
        self.current_device_index = 0  # Index of the device currently being processed
        self.num_of_ports = None # Number of port for a device
        _LOGGER.debug("MaxSmartConfigFlow initialized")

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        self._errors = {}

        if user_input is None:
            return await self.async_step_udp_discovery()
        elif CONF_IP_ADDRESS in user_input:
            # User input includes IP address, perform targeted discovery
            if is_valid_ipv4(user_input[CONF_IP_ADDRESS]):
                return await self.async_step_udp_discovery(user_input[CONF_IP_ADDRESS])
            else:
                self._errors[
                    "invalid_ip"
                ] = "component.maxsmart.config.error.invalid_ip"
                return self.show_ip_address_form()
        elif "add_manually" in user_input and not user_input["add_manually"]:
            return self.async_abort(reason="no_devices_found")
        elif "add_more" in user_input and user_input["add_more"] == "No":
            return self.async_abort(reason="configuration_complete")

        # If we reach this point, we should show the form to ask for an IP address
        return self.show_ip_address_form()

    def show_ip_address_form(self):
        """Show the form to ask for an IP address."""
        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA_MANUAL,
            errors=self._errors,
        )

    async def async_step_add_more_devices(self, user_input=None):
        """Step to add more devices by IP address."""
        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA_ADD_MORE,
            errors=self._errors,
        )

    async def async_step_udp_discovery(self, ip_address=None):
        """Perform device discovery and return the results."""

        if ip_address is not None:
            # Targeted discovery for a specific IP address
            _LOGGER.info(
                "Performing UDP unicast discovery towards ip %s on port 8888",
                ip_address,
            )
            self.devices = await self.hass.async_add_executor_job(
                MaxSmartDiscovery.discover_maxsmart, ip_address
            )
        else:
            # Broadcast discovery for all devices on the network
            _LOGGER.info("Performing UDP broadcast discovery on port 8888")
            self.devices = await self.hass.async_add_executor_job(
                MaxSmartDiscovery.discover_maxsmart
            )

        if self.devices:
            _LOGGER.debug("Devices discovered: %s", self.devices)
            # Process each discovered device
            for device in self.devices:
                # Check if a configuration entry already exists for this device
                existing_entry = next(
                    (
                        entry
                        for entry in self._async_current_entries()
                        if entry.unique_id == device["sn"]
                    ),
                    None,
                )
                if existing_entry:
                    _LOGGER.info(
                        "Device %s with name %s is already configured",
                        device["sn"],
                        device["name"],
                    )
                    continue  # Skip to the next device

                # Process the data for this device
                return await self.async_step_process_data(device)

            # If you reach this point, all devices have been processed or skipped
            # You can handle the finalization logic here, if needed
        else:
            return self.show_ip_address_form()

    async def async_step_process_data(self, device=None, user_input=None):
        """Process devices."""
        _LOGGER.debug("Processing device: %s", device)

        if user_input is None:
            _LOGGER.debug("If user input is NONE")

            if device is not None:
                self.device_data = device
            _LOGGER.debug("Self device data is : %s", self.device_data)
            _LOGGER.debug("GETTING IP Address where user input is NONE")

            ip_address = self.device_data["ip"]
            self.num_of_ports = await async_get_number_of_ports(self.hass, ip_address)
            device_name = self.device_data.get(
                "name", ""
            )  # Get the existing device name if available

            # Choose the appropriate schema based on the number of ports and version
            if self.device_data["ver"] == "1.30" and self.num_of_ports == 6:
                _LOGGER.debug("Showing multi-port form")

                schema = DATA_SCHEMA_MULTI_PORTS
            else:
                _LOGGER.debug("Showing SINGLE port form")
                schema = vol.Schema(
                    {
                        vol.Required(CONF_DEVICE_NAME, description="Device Name",default=device_name,): vol.All(
                            str, vol.Length(min=1)
                        ),
                        vol.Required(CONF_PORT1_NAME, description="Port 1 Name"): vol.All(
                            str, vol.Length(min=1)
                        )
                    }
                )
#                schema = DATA_SCHEMA_MULTI_PORTS

            return self.async_show_form(
                step_id="process_data",
                data_schema=schema,
                description_placeholders={
                    "ip": ip_address,
                    "sn": self.device_data["sn"],
                    "np": self.num_of_ports,
                },
                errors={},
            )

        else:
            # Update the name and pname fields of the current device according to user input
            _LOGGER.debug("Processing input and updating data")
            if "device_name" in user_input:
                self.device_data["name"] = user_input["device_name"]
            if self.num_of_ports == 6:
                self.device_data["pname"] = [
                    user_input.get(f"port{i}_name")
                    for i in range(1, 7)
                    if user_input.get(f"port{i}_name")
                ]
            else:
                self.device_data["pname"] = [
                    user_input.get(f"port1_name")
                ]

    async def process_import_step(self):
        """Process the import step for all devices."""
        for device in self.devices:
            await self.hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_IMPORT}, data=device
            )
        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA_ADD_MORE,
            errors={},
        )

    async def async_step_import(self, device):
        """Create entry for a device"""
        try:
            pname = device.get("pname")
            # sw_version = device.get("ver")

            port_data = {
                "master": {"port_id": 0, "port_name": "0. Master"},
                "individual_ports": [
                    {"port_id": i + 1, "port_name": f"{i + 1}. {port_name}"}
                    for i, port_name in enumerate(pname)
                ],
            }

            device_data = {
                "device_unique_id": device["sn"],
                "device_ip": device["ip"],
                "device_name": device["name"],
                "sw_version": device["ver"],
                "ports": port_data,
            }

            await self.async_set_unique_id(device["sn"])

            current_entries = self._async_current_entries()
            existing_entry = next(
                (entry for entry in current_entries if entry.unique_id == device["sn"]),
                None,
            )

            if existing_entry:
                _LOGGER.info(
                    "Device %s with name %s is already configured",
                    device["sn"],
                    device["name"],
                )
                if existing_entry.data != device_data:
                    _LOGGER.info("Updating config entry for device %s", device["sn"])
                    self.hass.config_entries.async_update_entry(
                        existing_entry, data=device_data
                    )
                    return self.async_show_form(
                        step_id="import",
                        data_schema=DATA_SCHEMA_OVERWRITE,
                        description_placeholders={
                            "ip": device["ip"],
                            "sn": device["sn"],
                        },
                        errors={},
                    )

            _LOGGER.debug("Creating entry for device %s", device["sn"])
            return self.async_create_entry(
                title=f"maxsmart_{device['sn']}",
                data=device_data,
            )

        except Exception as err:
            _LOGGER.error("Failed to create device entry: %s", err)
            return self.async_abort(reason="device_creation_failed")
