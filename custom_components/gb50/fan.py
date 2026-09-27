"""Dynamic Fan platform for Mitsubishi GB-50 LOSSNAY HRU ventilation units."""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from homeassistant.components.fan import (
    FanEntity,
    FanEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from .const import (
    DOMAIN,
    MODEL_LC,
    SIGNAL_NEW_GROUP_DISCOVERED,
    SIGNAL_GROUP_UPDATED,
    MODE_LC_AUTO,
    MODE_BYPASS,
    MODE_HEATRECOVERY,
)
from .coordinator import GB50DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

ORDERED_FAN_SPEEDS = ["LOW", "HIGH"]
PRESET_MODES = [MODE_LC_AUTO, MODE_BYPASS, MODE_HEATRECOVERY]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up dynamically discovered LOSSNAY fan entities."""
    coordinator: GB50DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    created_group_ids: set[int] = set()

    @callback
    def add_lossnay_entity(group_data: Dict[str, Any]) -> None:
        gid = group_data.get("group_id")
        if gid is None or gid in created_group_ids:
            return

        model = group_data.get("model")
        # Only instantiate FanEntity for LOSSNAY (LC) units
        if model == MODEL_LC:
            created_group_ids.add(gid)
            async_add_entities([GB50LossnayFanEntity(coordinator, entry, gid)])

    # 1. Register currently discovered LOSSNAY units
    for group in coordinator.groups.values():
        add_lossnay_entity(group)

    # 2. Dynamic discovery signal listener
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_GROUP_DISCOVERED.format(entry_id=entry.entry_id),
            add_lossnay_entity,
        )
    )


class GB50LossnayFanEntity(CoordinatorEntity[GB50DataUpdateCoordinator], FanEntity):
    """Dynamic Fan entity representing a Mitsubishi LOSSNAY heat recovery ventilator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GB50DataUpdateCoordinator,
        entry: ConfigEntry,
        group_id: int,
    ) -> None:
        """Initialize the LOSSNAY fan entity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entry = entry
        self.group_id = group_id
        
        mac = coordinator.system_info.get("mac_address", entry.entry_id)
        self._attr_unique_id = f"{mac}_group_{group_id}_fan"
        self._update_cached_state()

    def _get_group_data(self) -> Dict[str, Any]:
        return self.coordinator.groups.get(self.group_id, {})

    @callback
    def _update_cached_state(self) -> None:
        """Update internal attributes from group telemetry."""
        group = self._get_group_data()
        name = group.get("room_name") or group.get("name") or f"LOSSNAY {self.group_id}"
        self._attr_name = name

        mac = self.coordinator.system_info.get("mac_address", self.entry.entry_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self.entry.entry_id}_group_{self.group_id}")},
            name=name,
            manufacturer="Mitsubishi Electric",
            model=f"LOSSNAY Energy Recovery Ventilator (M-Net {group.get('address', self.group_id)})",
            suggested_area=group.get("area_name", "Ventilation"),
            via_device=(DOMAIN, mac),
        )

    @property
    def available(self) -> bool:
        return self.coordinator.is_connected and self.group_id in self.coordinator.groups

    @property
    def is_on(self) -> bool:
        """Return True if the ventilator is currently running."""
        return self._get_group_data().get("drive") == "ON"

    @property
    def percentage(self) -> Optional[int]:
        """Return current speed as percentage."""
        speed = self._get_group_data().get("fan_speed", "LOW")
        if speed not in ORDERED_FAN_SPEEDS:
            return 50
        return ordered_list_item_to_percentage(ORDERED_FAN_SPEEDS, speed)

    @property
    def speed_count(self) -> int:
        """Return available speed steps (Low, High)."""
        return len(ORDERED_FAN_SPEEDS)

    @property
    def preset_mode(self) -> Optional[str]:
        """Return active ventilation mode (LC_AUTO, BYPASS, HEATRECOVERY)."""
        return self._get_group_data().get("mode")

    @property
    def preset_modes(self) -> List[str]:
        """Supported ventilation modes."""
        return PRESET_MODES

    @property
    def supported_features(self) -> FanEntityFeature:
        """Dynamically compute supported fan features."""
        return (
            FanEntityFeature.SET_SPEED
            | FanEntityFeature.PRESET_MODE
            | FanEntityFeature.TURN_ON
            | FanEntityFeature.TURN_OFF
        )

    async def async_turn_on(
        self,
        percentage: Optional[int] = None,
        preset_mode: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the ventilator with optional speed or preset mode."""
        update_kwargs: Dict[str, Any] = {"drive": "ON"}
        if percentage is not None:
            speed = percentage_to_ordered_list_item(ORDERED_FAN_SPEEDS, percentage)
            update_kwargs["fan_speed"] = speed
        if preset_mode is not None and preset_mode in PRESET_MODES:
            update_kwargs["mode"] = preset_mode

        await self.coordinator.client.set_group(self.group_id, **update_kwargs)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the ventilator."""
        await self.coordinator.client.set_group(self.group_id, drive="OFF")

    async def async_set_percentage(self, percentage: int) -> None:
        """Set fan speed percentage."""
        if percentage == 0:
            await self.async_turn_off()
            return
        speed = percentage_to_ordered_list_item(ORDERED_FAN_SPEEDS, percentage)
        await self.coordinator.client.set_group(self.group_id, drive="ON", fan_speed=speed)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set ventilation preset mode (Auto, Bypass, Heat Recovery)."""
        if preset_mode in PRESET_MODES:
            await self.coordinator.client.set_group(self.group_id, mode=preset_mode)

    async def async_added_to_hass(self) -> None:
        """Subscribe to individual group update signals."""
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
