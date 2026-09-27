"""Dynamic Climate platform for Mitsubishi GB-50 indoor HVAC units."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
)
from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_LOW,
    FAN_HIGH,
    SWING_AUTO,
    SWING_HORIZONTAL,
    SWING_VERTICAL,
    SWING_ON,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MODEL_IC,
    SIGNAL_NEW_GROUP_DISCOVERED,
    SIGNAL_GROUP_UPDATED,
    MODE_OFF,
    MODE_HEAT,
    MODE_COOL,
    MODE_FAN,
    MODE_DRY,
    MODE_AUTO,
    MODE_AUTOHEAT,
    MODE_AUTOCOOL,
)
from .coordinator import GB50DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Enums and Mappings
HA_TO_GB50_MODE = {
    HVACMode.OFF: "OFF",
    HVACMode.HEAT: "HEAT",
    HVACMode.COOL: "COOL",
    HVACMode.FAN_ONLY: "FAN",
    HVACMode.DRY: "DRY",
    HVACMode.AUTO: "AUTO",
}

GB50_TO_HA_MODE = {
    "OFF": HVACMode.OFF,
    "HEAT": HVACMode.HEAT,
    "COOL": HVACMode.COOL,
    "FAN": HVACMode.FAN_ONLY,
    "DRY": HVACMode.DRY,
    "AUTO": HVACMode.AUTO,
    "AUTOHEAT": HVACMode.AUTO,
    "AUTOCOOL": HVACMode.AUTO,
}

FAN_MODE_MAP_TO_GB50 = {
    "auto": "AUTO",
    "low": "LOW",
    "mid2": "MID2",
    "mid1": "MID1",
    "high": "HIGH",
}

FAN_MODE_MAP_TO_HA = {
    "AUTO": "auto",
    "LOW": "low",
    "MID2": "mid2",
    "MID1": "mid1",
    "HIGH": "high",
}

SWING_MODE_MAP_TO_GB50 = {
    "auto": "AUTO",
    "horizontal": "HORIZONTAL",
    "mid1": "MID1",
    "mid2": "MID2",
    "vertical": "VERTICAL",
    "swing": "SWING",
}

SWING_MODE_MAP_TO_HA = {
    "AUTO": "auto",
    "HORIZONTAL": "horizontal",
    "MID1": "mid1",
    "MID2": "mid2",
    "VERTICAL": "vertical",
    "SWING": "swing",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up dynamically discovered GB-50 climate entities."""
    coordinator: GB50DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    created_group_ids: set[int] = set()

    @callback
    def add_group_entity(group_data: Dict[str, Any]) -> None:
        gid = group_data.get("group_id")
        if gid is None or gid in created_group_ids:
            return

        model = group_data.get("model", MODEL_IC)
        # Register climate entity only for Indoor AC Units (IC)
        if model == MODEL_IC or model not in ("LC", "PLC", "SC"):
            created_group_ids.add(gid)
            async_add_entities([GB50ClimateEntity(coordinator, entry, gid)])

    # 1. Register currently discovered groups
    for group in coordinator.groups.values():
        add_group_entity(group)

    # 2. Listen for runtime dynamic group discovery
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_GROUP_DISCOVERED.format(entry_id=entry.entry_id),
            add_group_entity,
        )
    )


class GB50ClimateEntity(CoordinatorEntity[GB50DataUpdateCoordinator], ClimateEntity):
    """Dynamic Climate entity representing a Mitsubishi GB-50 indoor zone."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GB50DataUpdateCoordinator,
        entry: ConfigEntry,
        group_id: int,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entry = entry
        self.group_id = group_id
        
        mac = coordinator.system_info.get("mac_address", entry.entry_id)
        self._attr_unique_id = f"{mac}_group_{group_id}_climate"
        self._update_cached_state()

    def _get_group_data(self) -> Dict[str, Any]:
        return self.coordinator.groups.get(self.group_id, {})

    def _get_capabilities(self) -> Dict[str, Any]:
        return self._get_group_data().get("capabilities", {})

    @callback
    def _update_cached_state(self) -> None:
        """Update internal attributes from latest group telemetry."""
        group = self._get_group_data()
        name = group.get("room_name") or group.get("name") or f"Zone {self.group_id}"
        self._attr_name = name

        # Device Info grouping
        mac = self.coordinator.system_info.get("mac_address", self.entry.entry_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self.entry.entry_id}_group_{self.group_id}")},
            name=name,
            manufacturer="Mitsubishi Electric",
            model=f"Indoor Unit (M-Net {group.get('address', self.group_id)})",
            suggested_area=group.get("area_name"),
            via_device=(DOMAIN, mac),
        )

    @property
    def available(self) -> bool:
        """Return True if coordinator is communicating and group exists."""
        return self.coordinator.is_connected and self.group_id in self.coordinator.groups

    @property
    def current_temperature(self) -> Optional[float]:
        """Return inlet/ambient temperature measured by the indoor unit."""
        return self._get_group_data().get("inlet_temp_c")

    @property
    def target_temperature(self) -> Optional[float]:
        """Return current setpoint temperature."""
        return self._get_group_data().get("set_temp_c")

    @property
    def hvac_mode(self) -> HVACMode:
        """Return active HVAC mode."""
        group = self._get_group_data()
        drive = group.get("drive", "OFF")
        if drive == "OFF":
            return HVACMode.OFF
        mode = group.get("mode", "COOL")
        return GB50_TO_HA_MODE.get(mode, HVACMode.COOL)

    @property
    def hvac_action(self) -> HVACAction:
        """Return current operating action."""
        group = self._get_group_data()
        drive = group.get("drive", "OFF")
        if drive == "OFF":
            return HVACAction.OFF
        mode = group.get("mode", "COOL")
        if mode in ("HEAT", "AUTOHEAT"):
            return HVACAction.HEATING
        if mode in ("COOL", "AUTOCOOL"):
            return HVACAction.COOLING
        if mode == "FAN":
            return HVACAction.FAN
        if mode == "DRY":
            return HVACAction.DRYING
        return HVACAction.IDLE

    @property
    def hvac_modes(self) -> List[HVACMode]:
        """Dynamically return supported HVAC modes from group capabilities."""
        caps = self._get_capabilities()
        modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.FAN_ONLY]
        if caps.get("has_dry_mode", True):
            modes.append(HVACMode.DRY)
        if caps.get("has_auto_mode", True):
            modes.append(HVACMode.AUTO)
        return modes

    @property
    def fan_mode(self) -> Optional[str]:
        """Return current fan stage."""
        speed = self._get_group_data().get("fan_speed", "AUTO")
        return FAN_MODE_MAP_TO_HA.get(speed, "auto")

    @property
    def fan_modes(self) -> Optional[List[str]]:
        """Dynamically return available fan speed stages."""
        caps = self._get_capabilities()
        if not caps.get("has_fan_speed", True):
            return None
        stages = caps.get("fan_speed_stages", 4)
        if stages <= 2:
            return ["auto", "low", "high"]
        return ["auto", "low", "mid2", "mid1", "high"]

    @property
    def swing_mode(self) -> Optional[str]:
        """Return current louver air direction."""
        direction = self._get_group_data().get("air_direction", "AUTO")
        return SWING_MODE_MAP_TO_HA.get(direction, "auto")

    @property
    def swing_modes(self) -> Optional[List[str]]:
        """Dynamically return available swing/vane directions."""
        caps = self._get_capabilities()
        if not caps.get("has_air_direction", True) and not caps.get("has_swing", True):
            return None
        modes = ["auto", "horizontal", "mid1", "mid2", "vertical"]
        if caps.get("has_swing", True):
            modes.append("swing")
        return modes

    @property
    def min_temp(self) -> float:
        """Dynamic minimum temperature setpoint."""
        caps = self._get_capabilities()
        return caps.get("temp_min_cool_c", 19.0)

    @property
    def max_temp(self) -> float:
        """Dynamic maximum temperature setpoint."""
        caps = self._get_capabilities()
        return caps.get("temp_max_heat_c", 28.0)

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Dynamically compute supported features based on unit capabilities."""
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        caps = self._get_capabilities()
        if caps.get("has_fan_speed", True):
            features |= ClimateEntityFeature.FAN_MODE
        if caps.get("has_air_direction", True) or caps.get("has_swing", True):
            features |= ClimateEntityFeature.SWING_MODE
        return features

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target setpoint temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self.coordinator.client.set_group(self.group_id, set_temp_c=round(float(temp), 1))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set drive state and operating mode."""
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.client.set_group(self.group_id, drive="OFF")
            return
        
        gb50_mode = HA_TO_GB50_MODE.get(hvac_mode)
        if gb50_mode:
            await self.coordinator.client.set_group(self.group_id, drive="ON", mode=gb50_mode)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan speed stage."""
        gb50_speed = FAN_MODE_MAP_TO_GB50.get(fan_mode.lower())
        if gb50_speed:
            await self.coordinator.client.set_group(self.group_id, fan_speed=gb50_speed)

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set louver vane swing position."""
        gb50_dir = SWING_MODE_MAP_TO_GB50.get(swing_mode.lower())
        if gb50_dir:
            await self.coordinator.client.set_group(self.group_id, air_direction=gb50_dir)

    async def async_turn_on(self) -> None:
        """Turn on the unit."""
        await self.coordinator.client.set_group(self.group_id, drive="ON")

    async def async_turn_off(self) -> None:
        """Turn off the unit."""
        await self.coordinator.client.set_group(self.group_id, drive="OFF")

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
        """Handle targeted group update."""
        self._update_cached_state()
        self.async_write_ha_state()
