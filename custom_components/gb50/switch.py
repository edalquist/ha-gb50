"""Dynamic Switch platform for Mitsubishi GB-50 general equipment and PLC relays."""

from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MODEL_PLC,
    SIGNAL_NEW_GROUP_DISCOVERED,
    SIGNAL_GROUP_UPDATED,
)
from .coordinator import GB50DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up dynamically discovered general equipment switch entities."""
    coordinator: GB50DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    created_group_ids: set[int] = set()

    @callback
    def add_switch_entity(group_data: Dict[str, Any]) -> None:
        gid = group_data.get("group_id")
        if gid is None or gid in created_group_ids:
            return

        model = group_data.get("model")
        if model == MODEL_PLC:
            created_group_ids.add(gid)
            async_add_entities([GB50GeneralEquipmentSwitch(coordinator, entry, gid)])

    # 1. Initial discovered PLC units
    for group in coordinator.groups.values():
        add_switch_entity(group)

    # 2. Dynamic discovery listener
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_GROUP_DISCOVERED.format(entry_id=entry.entry_id),
            add_switch_entity,
        )
    )


class GB50GeneralEquipmentSwitch(CoordinatorEntity[GB50DataUpdateCoordinator], SwitchEntity):
    """Switch entity representing general equipment / PLC relay on the GB-50."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GB50DataUpdateCoordinator,
        entry: ConfigEntry,
        group_id: int,
    ) -> None:
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entry = entry
        self.group_id = group_id
        
        mac = coordinator.system_info.get("mac_address", entry.entry_id)
        self._attr_unique_id = f"{mac}_group_{group_id}_switch"
        self._update_cached_state()

    def _get_group_data(self) -> Dict[str, Any]:
        return self.coordinator.groups.get(self.group_id, {})

    @callback
    def _update_cached_state(self) -> None:
        group = self._get_group_data()
        name = group.get("room_name") or group.get("name") or f"Equipment {self.group_id}"
        self._attr_name = name

        mac = self.coordinator.system_info.get("mac_address", self.entry.entry_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self.entry.entry_id}_group_{self.group_id}")},
            name=name,
            manufacturer="Mitsubishi Electric",
            model=f"General Equipment Relay (M-Net {group.get('address', self.group_id)})",
            suggested_area=group.get("area_name"),
            via_device=(DOMAIN, mac),
        )

    @property
    def available(self) -> bool:
        return self.coordinator.is_connected and self.group_id in self.coordinator.groups

    @property
    def is_on(self) -> bool:
        return self._get_group_data().get("drive") == "ON"

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_group(self.group_id, drive="ON")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_group(self.group_id, drive="OFF")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_GROUP_UPDATED.format(entry_id=self.entry.entry_id, group_id=self.group_id),
                self._handle_group_update,
            )
        )

    @callback
    def _handle_group_update(self, group_data: Dict[str, Any]) -> None:
        self._update_cached_state()
        self.async_write_ha_state()
