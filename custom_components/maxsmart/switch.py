# custom_components/maxsmart/switch.py
"""Platform for switch integration."""

from __future__ import annotations

import logging
from typing import Any, Optional

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
    
    entities = []
    
    # Create master switch (port 0)
    entities.append(
        MaxSmartSwitchEntity(
            coordinator=coordinator,
            device_unique_id=device_unique_id,
            device_name=device_name,
            port_id=0,
            port_name="Master",
        )
    )
    
    # Create individual port switches (assume 6 ports for now)
    for port_id in range(1, 7):
        entities.append(
            MaxSmartSwitchEntity(
                coordinator=coordinator,
                device_unique_id=device_unique_id,
                device_name=device_name,
                port_id=port_id,
                port_name=f"Port {port_id}",
            )
        )
    
    async_add_entities(entities)
    _LOGGER.info("Added %d MaxSmart switch entities", len(entities))

class MaxSmartSwitchEntity(CoordinatorEntity[MaxSmartCoordinator], SwitchEntity):
    """MaxSmart switch entity."""

    def __init__(
        self,
        coordinator: MaxSmartCoordinator,
        device_unique_id: str,
        device_name: str,
        port_id: int,
        port_name: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        
        self._device_unique_id = device_unique_id
        self._device_name = device_name
        self._port_id = port_id
        self._port_name = port_name
        
        self._attr_unique_id = f"{device_unique_id}_{port_id}"
        self._attr_name = f"{device_name} {port_name}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_unique_id)},
            "name": f"MaxSmart {device_name}",
            "manufacturer": "Max Hauri",
            "model": "MaxSmart Power Station",
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and super().available

    @property
    def is_on(self) -> Optional[bool]:
        """Return true if switch is on."""
        if not self.coordinator.data:
            return None
            
        try:
            switch_list = self.coordinator.data.get("switch", [])
            
            if self._port_id == 0:  # Master switch
                return any(state == 1 for state in switch_list)
            else:  # Individual port
                if 1 <= self._port_id <= len(switch_list):
                    return switch_list[self._port_id - 1] == 1
                return None
                    
        except (TypeError, IndexError):
            return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.coordinator.async_turn_on(self._port_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.coordinator.async_turn_off(self._port_id)