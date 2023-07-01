import logging
from homeassistant import config_entries, exceptions
from homeassistant.const import CONF_IP_ADDRESS
import voluptuous as vol
from .const import DOMAIN
from maxsmart import MaxSmartDiscovery

_LOGGER = logging.getLogger(__name__)


class MaxSmartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Example config flow."""

    VERSION = 1

    async def async_step_discovery(self, user_input=None):
        """Handle a flow initialized by discovery."""
        _LOGGER.debug("Starting device discovery.")
        devices = await self.hass.async_add_executor_job(
            MaxSmartDiscovery.discover_maxsmart
        )
        _LOGGER.debug(f"Discovered devices: {devices}")

        if len(devices) > 0:
            return await self.async_step_create_entries(devices)

        _LOGGER.warning("No devices found in discovery.")
        return self.async_abort(reason="no_devices_found")

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is None:
            _LOGGER.debug("Starting user-initiated device discovery without IP.")
            devices = await self.hass.async_add_executor_job(
                MaxSmartDiscovery.discover_maxsmart
            )
            _LOGGER.debug(f"Discovered devices: {devices}")

            if devices:
                return await self.async_step_create_entries(devices)
            else:
                return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema({vol.Required(CONF_IP_ADDRESS): str}),
                    errors={"base": "no_devices_found"},
                )

        _LOGGER.debug(f"Starting user-initiated device discovery with IP: {user_input[CONF_IP_ADDRESS]}")
        devices = await self.hass.async_add_executor_job(
            MaxSmartDiscovery.discover_maxsmart, user_input[CONF_IP_ADDRESS]
        )
        _LOGGER.debug(f"Discovered devices: {devices}")

        if devices:
            return await self.async_step_create_entries(devices)
        else:
            errors["base"] = "no_devices_found"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_IP_ADDRESS): str}),
            errors=errors,
        )

    async def async_step_create_entries(self, devices):
        """Create entries for each discovered device."""
        for device in devices:
            try:
                pname = device.get("pname")
                port_data = {}

                if pname is None:
                    port_data["individual_ports"] = [
                        {"port_id": 1, "port_name": device["name"]}
                    ]
                else:
                    port_data = {
                        "master": {"port_id": 0, "port_name": "Master"},
                        "individual_ports": [
                            {"port_id": i + 1, "port_name": port_name}
                            for i, port_name in enumerate(pname)
                        ],
                    }

                device_data = {
                    "device_unique_id": device["sn"],
                    "device_ip": device["ip"],
                    "device_name": device["name"],
                    "ports": port_data,
                }

                _LOGGER.debug(f"Creating entry for device: {device_data}")

                await self.async_set_unique_id(device["sn"])
                self._abort_if_unique_id_configured()

                self.async_create_entry(
                    title=device["name"],
                    data=device_data,
                )

            except Exception as err:
                _LOGGER.error("Failed to create device entry: %s", err)
