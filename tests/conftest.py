"""Test configuration, fixtures, and mock proxy responses for ha-gb50."""

import sys
import types
from enum import Enum, IntFlag
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock
import pytest


# =========================================================================
# Lightweight Home Assistant Stubs for Standalone Unit Testing
# =========================================================================

if "voluptuous" not in sys.modules:
    vol = types.ModuleType("voluptuous")
    vol.Schema = lambda schema: schema
    vol.Required = lambda key, default=None: key
    vol.Optional = lambda key, default=None: key
    sys.modules["voluptuous"] = vol

if "homeassistant" not in sys.modules:
    ha = types.ModuleType("homeassistant")
    ha_const = types.ModuleType("homeassistant.const")
    ha_core = types.ModuleType("homeassistant.core")
    ha_config_entries = types.ModuleType("homeassistant.config_entries")
    ha_helpers = types.ModuleType("homeassistant.helpers")
    ha_helpers_uc = types.ModuleType("homeassistant.helpers.update_coordinator")
    ha_helpers_disp = types.ModuleType("homeassistant.helpers.dispatcher")
    ha_helpers_entity = types.ModuleType("homeassistant.helpers.entity")
    ha_helpers_ep = types.ModuleType("homeassistant.helpers.entity_platform")
    ha_helpers_aio = types.ModuleType("homeassistant.helpers.aiohttp_client")
    ha_comp = types.ModuleType("homeassistant.components")
    ha_climate = types.ModuleType("homeassistant.components.climate")
    ha_climate_const = types.ModuleType("homeassistant.components.climate.const")
    ha_fan = types.ModuleType("homeassistant.components.fan")
    ha_switch = types.ModuleType("homeassistant.components.switch")
    ha_bs = types.ModuleType("homeassistant.components.binary_sensor")
    ha_button = types.ModuleType("homeassistant.components.button")
    ha_sensor = types.ModuleType("homeassistant.components.sensor")
    ha_util = types.ModuleType("homeassistant.util")
    ha_util_pct = types.ModuleType("homeassistant.util.percentage")

    # Enums
    class UnitOfTemperature(str, Enum):
        CELSIUS = "°C"
        FAHRENHEIT = "°F"

    class Platform(str, Enum):
        CLIMATE = "climate"
        FAN = "fan"
        SWITCH = "switch"
        BINARY_SENSOR = "binary_sensor"
        BUTTON = "button"
        SENSOR = "sensor"

    class HVACMode(str, Enum):
        OFF = "off"
        HEAT = "heat"
        COOL = "cool"
        FAN_ONLY = "fan_only"
        DRY = "dry"
        AUTO = "auto"

    class HVACAction(str, Enum):
        OFF = "off"
        HEATING = "heating"
        COOLING = "cooling"
        FAN = "fan"
        DRYING = "drying"
        IDLE = "idle"

    class ClimateEntityFeature(IntFlag):
        TARGET_TEMPERATURE = 1
        FAN_MODE = 2
        SWING_MODE = 4
        TURN_ON = 8
        TURN_OFF = 16

    class FanEntityFeature(IntFlag):
        SET_SPEED = 1
        PRESET_MODE = 2
        TURN_ON = 4
        TURN_OFF = 8

    class BinarySensorDeviceClass(str, Enum):
        PROBLEM = "problem"
        CONNECTIVITY = "connectivity"

    class SensorDeviceClass(str, Enum):
        TEMPERATURE = "temperature"

    class SensorStateClass(str, Enum):
        MEASUREMENT = "measurement"

    class EntityCategory(str, Enum):
        DIAGNOSTIC = "diagnostic"
        CONFIG = "config"

    # Base Entity Classes
    class DeviceInfo(dict):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

    class MockEntity:
        _attr_unique_id: Optional[str] = None
        _attr_name: Optional[str] = None
        _attr_device_info: Optional[DeviceInfo] = None
        _attr_has_entity_name = True

        @property
        def name(self) -> Optional[str]:
            return self._attr_name

        def async_write_ha_state(self):
            pass

        async def async_added_to_hass(self):
            pass

        def async_on_remove(self, func):
            pass

    class CoordinatorEntity(MockEntity):
        def __init__(self, coordinator):
            self.coordinator = coordinator

        def __class_getitem__(cls, item):
            return cls

    class ClimateEntity(MockEntity):
        pass

    class FanEntity(MockEntity):
        pass

    class SwitchEntity(MockEntity):
        pass

    class BinarySensorEntity(MockEntity):
        pass

    class ButtonEntity(MockEntity):
        pass

    class SensorEntity(MockEntity):
        pass

    class DataUpdateCoordinator:
        def __init__(self, hass, logger, name, update_interval=None):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = None

        def __class_getitem__(cls, item):
            return cls

        def async_set_updated_data(self, data):
            self.data = data

    class UpdateFailed(Exception):
        pass

    class ConfigEntry:
        def __init__(self, entry_id="test_entry_id", data=None):
            self.entry_id = entry_id
            self.data = data or {}

        def async_on_unload(self, callback):
            pass

    def callback(func):
        return func

    def async_dispatcher_send(hass, signal, *args):
        pass

    def async_dispatcher_connect(hass, signal, target):
        return lambda: None

    def ordered_list_item_to_percentage(items, item):
        idx = items.index(item)
        return int((idx + 1) * 100 / len(items))

    def percentage_to_ordered_list_item(items, percentage):
        idx = min(len(items) - 1, max(0, int(percentage * len(items) / 100)))
        return items[idx]

    # Assign attributes
    ha_const.CONF_HOST = "host"
    ha_const.CONF_PORT = "port"
    ha_const.ATTR_TEMPERATURE = "temperature"
    ha_const.UnitOfTemperature = UnitOfTemperature
    ha_const.Platform = Platform

    ha_core.HomeAssistant = MagicMock if "MagicMock" in globals() else object
    ha_core.callback = callback

    ha_helpers_uc.DataUpdateCoordinator = DataUpdateCoordinator
    ha_helpers_uc.CoordinatorEntity = CoordinatorEntity
    ha_helpers_uc.UpdateFailed = UpdateFailed

    ha_helpers_disp.async_dispatcher_send = async_dispatcher_send
    ha_helpers_disp.async_dispatcher_connect = async_dispatcher_connect

    ha_helpers_entity.DeviceInfo = DeviceInfo
    ha_helpers_entity.EntityCategory = EntityCategory
    ha_helpers_ep.AddEntitiesCallback = Any

    ha_climate.ClimateEntity = ClimateEntity
    ha_climate.ClimateEntityFeature = ClimateEntityFeature
    ha_climate.HVACMode = HVACMode
    ha_climate.HVACAction = HVACAction
    ha_climate_const.FAN_AUTO = "auto"
    ha_climate_const.FAN_LOW = "low"
    ha_climate_const.FAN_HIGH = "high"
    ha_climate_const.SWING_AUTO = "auto"
    ha_climate_const.SWING_HORIZONTAL = "horizontal"
    ha_climate_const.SWING_VERTICAL = "vertical"
    ha_climate_const.SWING_ON = "swing"

    ha_fan.FanEntity = FanEntity
    ha_fan.FanEntityFeature = FanEntityFeature

    ha_switch.SwitchEntity = SwitchEntity

    ha_bs.BinarySensorEntity = BinarySensorEntity
    ha_bs.BinarySensorDeviceClass = BinarySensorDeviceClass

    ha_button.ButtonEntity = ButtonEntity

    ha_sensor.SensorEntity = SensorEntity
    ha_sensor.SensorDeviceClass = SensorDeviceClass
    ha_sensor.SensorStateClass = SensorStateClass

    ha_util_pct.ordered_list_item_to_percentage = ordered_list_item_to_percentage
    ha_util_pct.percentage_to_ordered_list_item = percentage_to_ordered_list_item

    ha_helpers_aio.async_get_clientsession = lambda hass: None

    class ConfigFlow:
        def __init_subclass__(cls, domain=None, **kwargs):
            super().__init_subclass__(**kwargs)
            cls.domain = domain

        def __init__(self):
            self.hass = MagicMock()
            self._unique_id = None

        async def async_set_unique_id(self, unique_id):
            self._unique_id = unique_id

        def _abort_if_unique_id_configured(self):
            pass

        def async_show_form(self, step_id, data_schema=None, errors=None):
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
            }

        def async_create_entry(self, title, data):
            return {
                "type": "create_entry",
                "title": title,
                "data": data,
            }

    ha_def = types.ModuleType("homeassistant.data_entry_flow")
    ha_def.FlowResult = Dict[str, Any]

    ha_config_entries.ConfigEntry = ConfigEntry
    ha_config_entries.ConfigFlow = ConfigFlow

    # Register in sys.modules
    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.const"] = ha_const
    sys.modules["homeassistant.core"] = ha_core
    sys.modules["homeassistant.data_entry_flow"] = ha_def
    sys.modules["homeassistant.config_entries"] = ha_config_entries
    sys.modules["homeassistant.helpers"] = ha_helpers
    sys.modules["homeassistant.helpers.update_coordinator"] = ha_helpers_uc
    sys.modules["homeassistant.helpers.dispatcher"] = ha_helpers_disp
    sys.modules["homeassistant.helpers.entity"] = ha_helpers_entity
    sys.modules["homeassistant.helpers.entity_platform"] = ha_helpers_ep
    sys.modules["homeassistant.helpers.aiohttp_client"] = ha_helpers_aio
    sys.modules["homeassistant.components"] = ha_comp
    sys.modules["homeassistant.components.climate"] = ha_climate
    sys.modules["homeassistant.components.climate.const"] = ha_climate_const
    sys.modules["homeassistant.components.fan"] = ha_fan
    sys.modules["homeassistant.components.switch"] = ha_switch
    sys.modules["homeassistant.components.binary_sensor"] = ha_bs
    sys.modules["homeassistant.components.button"] = ha_button
    sys.modules["homeassistant.components.sensor"] = ha_sensor
    sys.modules["homeassistant.util"] = ha_util
    sys.modules["homeassistant.util.percentage"] = ha_util_pct


# =========================================================================
# Fixtures
# =========================================================================

@pytest.fixture
def mock_system_info_payload() -> Dict[str, Any]:
    return {
        "version": "2.80",
        "model": "GB-50ADA-A",
        "serial_number": "11612-634",
        "system_name": "Saint Thomas Church",
        "location_id": "000001",
        "ip_address": "10.1.0.90",
        "mac_address": "0026926268AE",
        "temp_unit": "F",
        "licensed_functions": {"WebBrowse": True, "Schedule": True},
    }


@pytest.fixture
def mock_ac_group_payload() -> Dict[str, Any]:
    """Mock Indoor Air Conditioner unit (ModelType.IC)."""
    return {
        "group_id": 1,
        "name": "FC1-1",
        "room_name": "Sanctuary East",
        "area_name": "Floor 1",
        "floor": 1,
        "model": "IC",
        "address": 1,
        "slave_addresses": [],
        "drive": "OFF",
        "mode": "HEAT",
        "set_temp_c": 21.0,
        "set_temp_f": 69.8,
        "inlet_temp_c": 22.5,
        "inlet_temp_f": 72.5,
        "fan_speed": "AUTO",
        "air_direction": "HORIZONTAL",
        "filter_dirty": False,
        "error_active": False,
        "error_code": "0000",
        "capabilities": {
            "has_auto_mode": True,
            "has_dry_mode": True,
            "has_fan_speed": True,
            "has_air_direction": True,
            "has_swing": True,
            "fan_speed_stages": 4,
            "air_direction_stages": 5,
            "temp_min_cool_c": 19.0,
            "temp_max_cool_c": 30.0,
            "temp_min_heat_c": 17.0,
            "temp_max_heat_c": 28.0,
        },
    }


@pytest.fixture
def mock_lossnay_group_payload() -> Dict[str, Any]:
    """Mock LOSSNAY Energy Recovery Ventilator (ModelType.LC)."""
    return {
        "group_id": 27,
        "name": "HRU-1",
        "room_name": "Sanctuary Fresh Air",
        "area_name": "Ventilation",
        "floor": 1,
        "model": "LC",
        "address": 27,
        "slave_addresses": [],
        "drive": "ON",
        "mode": "LC_AUTO",
        "fan_speed": "HIGH",
        "air_direction": "AUTO",
        "filter_dirty": True,
        "error_active": False,
        "error_code": "0000",
        "capabilities": {
            "has_auto_mode": False,
            "has_dry_mode": False,
            "has_fan_speed": True,
            "has_air_direction": False,
            "has_swing": False,
            "has_ventilation": True,
            "has_bypass": True,
            "has_heat_recovery": True,
            "fan_speed_stages": 2,
        },
    }


@pytest.fixture
def mock_plc_group_payload() -> Dict[str, Any]:
    """Mock General Equipment Relay (ModelType.PLC)."""
    return {
        "group_id": 35,
        "name": "PUMP-1",
        "room_name": "Boiler Circulation Pump",
        "area_name": "Basement",
        "floor": 0,
        "model": "PLC",
        "address": 35,
        "slave_addresses": [],
        "drive": "ON",
        "mode": "OFF",
        "fan_speed": "AUTO",
        "air_direction": "AUTO",
        "filter_dirty": False,
        "error_active": False,
        "error_code": "0000",
        "capabilities": {},
    }
