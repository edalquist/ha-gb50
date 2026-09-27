"""Dynamic Button platform for Mitsubishi GB-50 filter resets and presets."""

from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SIGNAL_NEW_GROUP_DISCOVERED,
)
from .coordinator import GB50DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SYSTEM_PRESETS = [
    ("all_off", "All Units OFF", "mdi:power"),
    ("all_on", "All Units ON", "mdi:power-cycle"),
    ("occupied", "Occupied Preset", "mdi:account-group"),
    ("unoccupied", "Unoccupied Preset", "mdi:home-clock"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up dynamically discovered GB-50 buttons."""
    coordinator: GB50DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    created_group_ids: set[int] = set()

    # 1. System Presets on parent controller device
    system_buttons: list[ButtonEntity] = [
        GB50SystemPresetButton(coordinator, entry, preset_key, preset_label, icon)
        for preset_key, preset_label, icon in SYSTEM_PRESETS
    ]
    async_add_entities(system_buttons)

    # 2. Per-group filter reset buttons
    @callback
    def add_filter_button(group_data: Dict[str, Any]) -> None:
        gid = group_data.get("group_id")
        if gid is None or gid in created_group_ids:
            return
        created_group_ids.add(gid)
        async_add_entities([GB50FilterResetButton(coordinator, entry, gid)])

    for group in coordinator.groups.values():
        add_filter_button(group)

    # 3. Dynamic group listener
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_GROUP_DISCOVERED.format(entry_id=entry.entry_id),
            add_filter_button,
        )
    )


class GB50FilterResetButton(CoordinatorEntity[GB50DataUpdateCoordinator], ButtonEntity):
    """Button to reset the dirty filter sign on an individual HVAC zone."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:filter-check"
    _attr_has_entity_name = True
    _attr_name = "Reset Filter Sign"

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
        self._attr_unique_id = f"{mac}_group_{group_id}_reset_filter"

        group = self.coordinator.groups.get(self.group_id, {})
        name = group.get("room_name") or group.get("name") or f"Zone {group_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self.entry.entry_id}_group_{self.group_id}")},
            name=name,
            manufacturer="Mitsubishi Electric",
            via_device=(DOMAIN, mac),
        )

    @property
    def available(self) -> bool:
        return self.coordinator.is_connected and self.group_id in self.coordinator.groups

    async def async_press(self) -> None:
        """Send filter reset command to the proxy."""
        _LOGGER.info("Resetting filter sign for group %s", self.group_id)
        await self.coordinator.client.reset_filter(self.group_id)


class GB50SystemPresetButton(CoordinatorEntity[GB50DataUpdateCoordinator], ButtonEntity):
    """Button to trigger quick whole-facility scene presets."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GB50DataUpdateCoordinator,
        entry: ConfigEntry,
        preset_key: str,
        preset_label: str,
        icon: str,
    ) -> None:
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entry = entry
        self.preset_key = preset_key
        self._attr_name = preset_label
        self._attr_icon = icon

        mac = coordinator.system_info.get("mac_address", entry.entry_id)
        self._attr_unique_id = f"{mac}_preset_{preset_key}"

        sys_name = coordinator.system_info.get("system_name") or "Mitsubishi GB-50"
        model = coordinator.system_info.get("model") or "GB-50"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=f"{sys_name} ({model})",
            manufacturer="Mitsubishi Electric",
        )

    @property
    def available(self) -> bool:
        return self.coordinator.is_connected

    async def async_press(self) -> None:
        """Trigger facility preset scene."""
        _LOGGER.info("Triggering GB-50 preset scene: %s", self.preset_key)
        await self.coordinator.client.apply_preset(self.preset_key)
