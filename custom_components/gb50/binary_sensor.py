"""Dynamic Binary Sensor platform for Mitsubishi GB-50 filter alerts and alarms."""

from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SIGNAL_NEW_GROUP_DISCOVERED,
    SIGNAL_GROUP_UPDATED,
    SIGNAL_SYSTEM_UPDATED,
)
from .coordinator import GB50DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up dynamically discovered GB-50 binary sensors."""
    coordinator: GB50DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    created_group_ids: set[int] = set()

    # 1. System controller connectivity sensor
    entities: list[BinarySensorEntity] = [
        GB50SystemConnectivityBinarySensor(coordinator, entry)
    ]

    @callback
    def add_group_sensors(group_data: Dict[str, Any]) -> None:
        gid = group_data.get("group_id")
        if gid is None or gid in created_group_ids:
            return
        created_group_ids.add(gid)

        new_sensors = [
            GB50FilterDirtyBinarySensor(coordinator, entry, gid),
            GB50GroupAlarmBinarySensor(coordinator, entry, gid),
        ]
        async_add_entities(new_sensors)

    # 2. Add existing groups
    for group in coordinator.groups.values():
        add_group_sensors(group)

    async_add_entities(entities)

    # 3. Dynamic group listener
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_GROUP_DISCOVERED.format(entry_id=entry.entry_id),
            add_group_sensors,
        )
    )


class GB50FilterDirtyBinarySensor(CoordinatorEntity[GB50DataUpdateCoordinator], BinarySensorEntity):
    """Binary sensor indicating dirty air filter requiring maintenance."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:air-filter"
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
        self._attr_unique_id = f"{mac}_group_{group_id}_filter_dirty"
        self._attr_translation_key = "filter_dirty"
        self._attr_name = "Filter Dirty"

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

    @property
    def is_on(self) -> bool:
        group = self.coordinator.groups.get(self.group_id, {})
        return bool(group.get("filter_dirty") or group.get("filter_sign"))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_GROUP_UPDATED.format(entry_id=self.entry.entry_id, group_id=self.group_id),
                lambda _: self.async_write_ha_state(),
            )
        )


class GB50GroupAlarmBinarySensor(CoordinatorEntity[GB50DataUpdateCoordinator], BinarySensorEntity):
    """Binary sensor indicating active hardware malfunction alarm for an indoor unit."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:alert-circle"
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
        self._attr_unique_id = f"{mac}_group_{group_id}_alarm"
        self._attr_name = "Hardware Alarm"

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

    @property
    def is_on(self) -> bool:
        group = self.coordinator.groups.get(self.group_id, {})
        return bool(group.get("error_active") or group.get("alarm_sign"))

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        group = self.coordinator.groups.get(self.group_id, {})
        attrs: Dict[str, Any] = {}
        if group.get("error_code"):
            attrs["error_code"] = group.get("error_code")
        return attrs

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_GROUP_UPDATED.format(entry_id=self.entry.entry_id, group_id=self.group_id),
                lambda _: self.async_write_ha_state(),
            )
        )


class GB50SystemConnectivityBinarySensor(CoordinatorEntity[GB50DataUpdateCoordinator], BinarySensorEntity):
    """Binary sensor indicating connection status to the central controller."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_name = "Controller Connection"

    def __init__(
        self,
        coordinator: GB50DataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entry = entry

        mac = coordinator.system_info.get("mac_address", entry.entry_id)
        self._attr_unique_id = f"{mac}_connectivity"

        sys_name = coordinator.system_info.get("system_name") or "Mitsubishi GB-50"
        model = coordinator.system_info.get("model") or "GB-50"
        version = coordinator.system_info.get("version")

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=f"{sys_name} ({model})",
            manufacturer="Mitsubishi Electric",
            model=model,
            sw_version=version,
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_connected

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_SYSTEM_UPDATED.format(entry_id=self.entry.entry_id),
                lambda: self.async_write_ha_state(),
            )
        )
