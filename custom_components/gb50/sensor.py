"""Dynamic Sensor platform for Mitsubishi GB-50 telemetry and diagnostics."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MODEL_IC,
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
    """Set up dynamically discovered GB-50 telemetry sensors."""
    coordinator: GB50DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    created_group_ids: set[int] = set()

    # 1. System level sensors
    system_sensors: list[SensorEntity] = [
        GB50ControllerFirmwareSensor(coordinator, entry),
    ]
    async_add_entities(system_sensors)

    # 2. Per-group telemetry sensors
    @callback
    def add_group_sensors(group_data: Dict[str, Any]) -> None:
        gid = group_data.get("group_id")
        if gid is None or gid in created_group_ids:
            return

        model = group_data.get("model", MODEL_IC)
        # Create intake temperature sensor for AC indoor units
        if model == MODEL_IC or model not in ("LC", "PLC", "SC"):
            created_group_ids.add(gid)
            async_add_entities([
                GB50InletTemperatureSensor(coordinator, entry, gid),
                GB50ErrorCodeSensor(coordinator, entry, gid),
            ])

    for group in coordinator.groups.values():
        add_group_sensors(group)

    # 3. Dynamic group discovery listener
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_GROUP_DISCOVERED.format(entry_id=entry.entry_id),
            add_group_sensors,
        )
    )


class GB50InletTemperatureSensor(CoordinatorEntity[GB50DataUpdateCoordinator], SensorEntity):
    """Room inlet / ambient temperature sensor measured by the indoor unit."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_has_entity_name = True
    _attr_name = "Room Temperature"

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
        self._attr_unique_id = f"{mac}_group_{group_id}_inlet_temp"

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
    def native_value(self) -> Optional[float]:
        group = self.coordinator.groups.get(self.group_id, {})
        return group.get("inlet_temp_c")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_GROUP_UPDATED.format(entry_id=self.entry.entry_id, group_id=self.group_id),
                lambda _: self.async_write_ha_state(),
            )
        )


class GB50ErrorCodeSensor(CoordinatorEntity[GB50DataUpdateCoordinator], SensorEntity):
    """Sensor reporting active 4-digit Mitsubishi diagnostic malfunction error code."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:wrench"
    _attr_has_entity_name = True
    _attr_name = "Error Code"

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
        self._attr_unique_id = f"{mac}_group_{group_id}_error_code"

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
    def native_value(self) -> Optional[str]:
        group = self.coordinator.groups.get(self.group_id, {})
        code = group.get("error_code")
        return code if code and code != "0000" else "Normal"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_GROUP_UPDATED.format(entry_id=self.entry.entry_id, group_id=self.group_id),
                lambda _: self.async_write_ha_state(),
            )
        )


class GB50ControllerFirmwareSensor(CoordinatorEntity[GB50DataUpdateCoordinator], SensorEntity):
    """Sensor reporting central controller firmware version."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_name = "Firmware Version"

    def __init__(
        self,
        coordinator: GB50DataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entry = entry

        mac = coordinator.system_info.get("mac_address", entry.entry_id)
        self._attr_unique_id = f"{mac}_firmware"

        sys_name = coordinator.system_info.get("system_name") or "Mitsubishi GB-50"
        model = coordinator.system_info.get("model") or "GB-50"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=f"{sys_name} ({model})",
            manufacturer="Mitsubishi Electric",
        )

    @property
    def native_value(self) -> Optional[str]:
        return self.coordinator.system_info.get("version")
