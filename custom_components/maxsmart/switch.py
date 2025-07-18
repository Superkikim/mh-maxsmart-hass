# custom_components/maxsmart/switch.py
"""Platform for switch integration using MaxSmart 2.0.0 coordinator."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MaxSmartCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MaxSmart switches from a config entry."""
    coordinator: MaxSmartCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    device_data = config_entry.data
    device_unique_id = device_data["device_unique_id"]
    device_name = device_data["device_name"]
    device_ports = device_data["ports"]
    device_version = device_data["sw_version"]
    
    # Determine device model based on port count
    port_count = len(device_ports["individual_ports"])
    device_model = "MaxSmart Smart Plug" if port_count == 1 else "MaxSmart Power Station"
    
    entities = []
    
    # Create master switch entity (port 0)
    master_port = device_ports["master"]
    entities.append(
        MaxSmartSwitchEntity(
            coordinator=coordinator,
            device_unique_id=device_unique_id,
            device_name=device_name,
            device_version=device_version,
            device_model=device_model,
            port_id=0,
            port_name=master_port["port_name"],
        )
    )
    
    # Create individual port switch entities
    for port in device_ports["individual_ports"]:
        entities.append(
            MaxSmartSwitchEntity(
                coordinator=coordinator,
                device_unique_id=device_unique_id,
                device_name=device_name,
                device_version=device_version,
                device_model=device_model,
                port_id=port["port_id"],
                port_name=port["port_name"],
            )
        )
    
    async_add_entities(entities)
    _LOGGER.debug("Added %d MaxSmart switch entities", len(entities))

class MaxSmartSwitchEntity(CoordinatorEntity[MaxSmartCoordinator], SwitchEntity):
    """Representation of a MaxSmart switch (master or individual port)."""

    def __init__(
        self,
        coordinator: MaxSmartCoordinator,
        device_unique_id: str,
        device_name: str,
        device_version: str,
        device_model: str,
        port_id: int,
        port_name: str,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        
        self._device_unique_id = device_unique_id
        self._device_name = device_name
        self._device_version = device_version
        self._device_model = device_model
        self._port_id = port_id
        self._port_name = port_name
        
        # Entity attributes
        self._attr_unique_id = f"{device_unique_id}_{port_id}"
        self._attr_name = f"{device_name} {port_name}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_unique_id)},
            "name": f"Maxsmart {device_name}",
            "manufacturer": "Max Hauri",
            "model": device_model,
            "sw_version": device_version,
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.is_available and super().available

    @property
    def is_on(self) -> Optional[bool]:
        """Return true if switch is on."""
        if not self.coordinator.data:
            return None
            
        try:
            switch_list = self.coordinator.data.get("switch", [])
            
            if self._port_id == 0:  # Master switch
                # Master is on if ANY individual port is on
                return any(state == 1 for state in switch_list)
            else:  # Individual port
                if 1 <= self._port_id <= len(switch_list):
                    return switch_list[self._port_id - 1] == 1
                else:
                    _LOGGER.warning("Invalid port_id %d for switch state", self._port_id)
                    return None
                    
        except (TypeError, IndexError) as err:
            _LOGGER.error("Error getting switch state for port %d: %s", self._port_id, err)
            return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        success = await self.coordinator.async_turn_on(self._port_id)
        if not success:
            _LOGGER.error("Failed to turn on %s (port %d)", self._attr_name, self._port_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        success = await self.coordinator.async_turn_off(self._port_id)
        if not success:
            _LOGGER.error("Failed to turn off %s (port %d)", self._attr_name, self._port_id)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        attributes = {
            "port_id": self._port_id,
            "device_ip": self.coordinator.device_ip,
            "firmware_version": self._device_version,
        }
        
        # Add power consumption if available
        power = self.coordinator.async_get_power_data(self._port_id)
        if power is not None:
            attributes["power_w"] = power
            
        return attributes