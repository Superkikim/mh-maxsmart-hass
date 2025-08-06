# custom_components/maxsmart/switch.py
"""Platform for switch integration using entity factory."""

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
from .entity_factory import MaxSmartEntityFactory

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MaxSmart switches from a config entry using entity factory."""
    coordinator: MaxSmartCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    # Create entity factory
    factory = MaxSmartEntityFactory(coordinator, config_entry)
    
    # Generate switch entity configurations
    switch_configs = factory.create_switch_entities()
    
    # Create actual switch entities
    entities = []
    for config in switch_configs:
        entities.append(MaxSmartSwitchEntity(**config))
    
    async_add_entities(entities, True)
    
    expected_count, _ = factory.get_entity_counts()
    _LOGGER.debug("Added %d/%d MaxSmart switch entities for %s",
                len(entities), expected_count, factory.device_name)

class MaxSmartSwitchEntity(CoordinatorEntity[MaxSmartCoordinator], SwitchEntity):
    """MaxSmart switch entity with smart capabilities."""

    def __init__(
        self,
        coordinator: MaxSmartCoordinator,
        device_unique_id: str,
        device_name: str,
        port_id: int,
        port_name: str,
        unique_id: str,
        name: str,
        device_info: dict,
        is_master: bool,
        **kwargs
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        
        self._device_unique_id = device_unique_id
        self._device_name = device_name
        self._port_id = port_id
        self._port_name = port_name
        self._is_master = is_master
        
        # Entity attributes
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._attr_device_info = device_info
        
        # Additional attributes for diagnostics
        self._attr_extra_state_attributes = {
            "port_id": port_id,
            "port_name": port_name,
            "is_master": is_master,
            "device_ip": coordinator.device_ip,
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
            
            if not switch_list:
                return None
                
            if self._is_master:
                # Master switch - true if ANY port is on
                return any(state == 1 for state in switch_list)
            else:
                # Individual port switch
                if 1 <= self._port_id <= len(switch_list):
                    return switch_list[self._port_id - 1] == 1
                return None
                    
        except (TypeError, IndexError) as err:
            _LOGGER.debug("Error getting switch state for port %d: %s", self._port_id, err)
            return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        try:
            success = await self.coordinator.async_turn_on(self._port_id)
            if not success:
                _LOGGER.error("Failed to turn on %s (port %d)", self._attr_name, self._port_id)
            else:
                _LOGGER.debug("Successfully turned on %s (port %d)", self._attr_name, self._port_id)
        except Exception as err:
            _LOGGER.error("Error turning on %s (port %d): %s", self._attr_name, self._port_id, err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        try:
            success = await self.coordinator.async_turn_off(self._port_id)
            if not success:
                _LOGGER.error("Failed to turn off %s (port %d)", self._attr_name, self._port_id)
            else:
                _LOGGER.debug("Successfully turned off %s (port %d)", self._attr_name, self._port_id)
        except Exception as err:
            _LOGGER.error("Error turning off %s (port %d): %s", self._attr_name, self._port_id, err)

    @property
    def icon(self) -> str:
        """Return the icon for this switch."""
        if self._is_master:
            return "mdi:power-socket-eu"
        else:
            return "mdi:power-socket"

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        await super().async_added_to_hass()
        # Removed verbose entity logging

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal."""
        await super().async_will_remove_from_hass()
        # Removed verbose entity logging