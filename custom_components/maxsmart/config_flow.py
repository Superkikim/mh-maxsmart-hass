import logging
from homeassistant import config_entries, exceptions
from homeassistant.const import CONF_IP_ADDRESS
import voluptuous as vol
from .const import DOMAIN, VERSION
from maxsmart import MaxSmartDiscovery, MaxSmartDevice

_LOGGER = logging.getLogger(__name__)

class MaxSmartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """MaxSmart Config Flow"""

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is None:
            _LOOGER.debug("Starting user-initiated device discovery without IP.")
            devices = await self.hass.async_add_executor_job(
                MaxSmartDiscovery.discover_maxsmart
            )
            _LOOGER.debug(f"Discovered devices without IP: {devices}")
        else:
            _LOOGER.debug("Starting user-initiated device discovery with IP.")
            devices = await self.hass.async_add_executor_job(
                MaxSmartDiscovery.discover_maxsmart, user_input[CONF_IP_ADDRESS]
            )
            _LOOGER.debug(f"Discovered devices with IP: {devices}")

        if devices:
            _LOOGER.debug("Devices have been found. Attempting to create entries")
            for device in devices:
                await self.hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": config_entries.SOURCE_IMPORT},
                    data=device
                )
            return self.async_abort(reason="devices_found")
        else:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({vol.Required(CONF_IP_ADDRESS): str}),
                errors={"base": "no_devices_found"},
            )

    _LOOGER.debug("Finished step user")

    async def async_step_import(self, device):
        """Create entry for a device"""
        ip_address = device["ip"]
        device_name = device["name"]
        num_of_ports = await async_get_number_of_ports(self.hass, ip_address)
        firmware = device["ver"]

        try:
            pname = device.get("pname")

            # sw_version = device.get("ver")
            port_data = {}

            if num_of_ports == 1:
                if firmware != "1.30":
                    device_name = ip_address
                port_data = {
                    "individual_ports": [
                        {"port_id": 1, "port_name": "1. Port"}
                    ],
                }
            elif num_of_ports == 6:
                if firmware != "1.30":
                    device_name = ip_address
                    pname = ["Port 1", "Port 2", "Port 3", "Port 4", "Port 5", "Port 6"]
                port_data = {
                    "individual_ports": [
                        {"port_id": i + 1, "port_name": f"{i + 1}. {port_name}"}
                        for i, port_name in enumerate(pname)
                    ],
                }

            # Count ports directly from individual_ports after setting them up
            num_of_ports = len(port_data.get("individual_ports", []))

            device_data = {
                "device_unique_id": device["sn"],
                "device_ip": device["ip"],
                "device_name": device_name,
                "sw_version": device["ver"],
                "ports": port_data,
            }

            await self.async_set_unique_id(device["sn"])

            current_entries = self._async_current_entries()
            existing_entry = next((entry for entry in current_entries if entry.unique_id == device["sn"]), None)

            if existing_entry:
                _LOOGER.debug("Device %s with name %s is already configured", device["sn"], device["name"])
                if existing_entry.data != device_data:
                    _LOOGER.debug("Updating config entry for device %s", device["sn"])
                    self.hass.config_entries.async_update_entry(existing_entry, data=device_data)
                return self.async_abort(reason="device_already_configured")

            return self.async_create_entry(
                title=f"maxsmart_{device['sn']}",
                data=device_data,
            )

        except Exception as err:
            _LOGGER.error("Failed to create device entry: %s", err)

