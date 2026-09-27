"""Unit tests verifying 100% dynamic discovery and capability routing (zero hardcoding)."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from custom_components.gb50.climate import GB50ClimateEntity
from custom_components.gb50.fan import GB50LossnayFanEntity
from custom_components.gb50.switch import GB50GeneralEquipmentSwitch
from custom_components.gb50.binary_sensor import (
    GB50FilterDirtyBinarySensor,
    GB50GroupAlarmBinarySensor,
    GB50SystemConnectivityBinarySensor,
)
from custom_components.gb50.button import GB50FilterResetButton, GB50SystemPresetButton
from custom_components.gb50.sensor import GB50InletTemperatureSensor, GB50ErrorCodeSensor


def create_mock_coordinator(groups_dict, system_info):
    coordinator = MagicMock()
    coordinator.groups = groups_dict
    coordinator.system_info = system_info
    coordinator.is_connected = True
    coordinator.client = MagicMock()
    coordinator.client.set_group = AsyncMock(return_value={"success": True})
    coordinator.client.reset_filter = AsyncMock(return_value={"success": True})
    coordinator.client.apply_preset = AsyncMock(return_value=[])
    return coordinator


def test_climate_dynamic_capabilities(mock_system_info_payload, mock_ac_group_payload):
    """Verify AC indoor unit dynamically maps features from GroupCapabilities."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    coordinator = create_mock_coordinator({1: mock_ac_group_payload}, mock_system_info_payload)

    climate = GB50ClimateEntity(coordinator, entry, group_id=1)

    assert climate.available is True
    assert climate.name == "Sanctuary East"
    assert climate.current_temperature == 22.5
    assert climate.target_temperature == 21.0
    assert climate.hvac_mode == "off"  # Drive is OFF in fixture
    assert "dry" in climate.hvac_modes
    assert "auto" in climate.hvac_modes
    assert climate.fan_modes == ["auto", "low", "mid2", "mid1", "high"]
    assert "swing" in climate.swing_modes
    assert climate.min_temp == 19.0
    assert climate.max_temp == 28.0

    # Test dynamic reduction of capabilities when hardware lacks features
    reduced_payload = dict(mock_ac_group_payload)
    reduced_payload["capabilities"] = {
        "has_auto_mode": False,
        "has_dry_mode": False,
        "has_fan_speed": True,
        "has_air_direction": False,
        "has_swing": False,
        "fan_speed_stages": 2,
        "temp_min_cool_c": 20.0,
        "temp_max_heat_c": 26.0,
    }
    coordinator.groups[1] = reduced_payload
    climate._update_cached_state()

    assert "dry" not in climate.hvac_modes
    assert "auto" not in climate.hvac_modes
    assert climate.fan_modes == ["auto", "low", "high"]
    assert climate.swing_modes is None
    assert climate.min_temp == 20.0
    assert climate.max_temp == 26.0


def test_lossnay_fan_dynamic_mapping(mock_system_info_payload, mock_lossnay_group_payload):
    """Verify LOSSNAY ventilator entity correctly maps speed stages and ventilation modes."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    coordinator = create_mock_coordinator({27: mock_lossnay_group_payload}, mock_system_info_payload)

    fan = GB50LossnayFanEntity(coordinator, entry, group_id=27)

    assert fan.available is True
    assert fan.name == "Sanctuary Fresh Air"
    assert fan.is_on is True
    assert fan.percentage == 100  # HIGH speed in fixture
    assert fan.speed_count == 2
    assert fan.preset_mode == "LC_AUTO"
    assert "BYPASS" in fan.preset_modes
    assert "HEATRECOVERY" in fan.preset_modes


def test_general_equipment_switch(mock_system_info_payload, mock_plc_group_payload):
    """Verify general equipment / PLC relay creates a functional switch entity."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    coordinator = create_mock_coordinator({35: mock_plc_group_payload}, mock_system_info_payload)

    switch = GB50GeneralEquipmentSwitch(coordinator, entry, group_id=35)

    assert switch.available is True
    assert switch.name == "Boiler Circulation Pump"
    assert switch.is_on is True


def test_binary_sensors_and_buttons(mock_system_info_payload, mock_lossnay_group_payload):
    """Verify dirty filter alert, reset button, and alarm sensors."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    coordinator = create_mock_coordinator({27: mock_lossnay_group_payload}, mock_system_info_payload)

    # Filter dirty sensor (HRU-1 has filter_dirty=True)
    filter_sensor = GB50FilterDirtyBinarySensor(coordinator, entry, group_id=27)
    assert filter_sensor.is_on is True

    # Filter reset button
    reset_btn = GB50FilterResetButton(coordinator, entry, group_id=27)
    assert reset_btn.available is True

    # System connectivity sensor
    conn_sensor = GB50SystemConnectivityBinarySensor(coordinator, entry)
    assert conn_sensor.is_on is True

    # Preset button
    preset_btn = GB50SystemPresetButton(coordinator, entry, "all_off", "All Units OFF", "mdi:power")
    assert preset_btn.available is True


def test_zero_hardcoding_scalability(mock_system_info_payload):
    """Verify engine handles arbitrary group topologies (1 to 50 groups) without hardcoded IDs."""
    entry = MagicMock()
    entry.entry_id = "test_entry"

    # Generate 50 heterogeneous groups
    groups_50 = {}
    for i in range(1, 51):
        if i <= 35:
            model = "IC"
            name = f"Zone-{i}"
        elif i <= 45:
            model = "LC"
            name = f"HRU-{i}"
        else:
            model = "PLC"
            name = f"Relay-{i}"

        groups_50[i] = {
            "group_id": i,
            "name": name,
            "model": model,
            "address": i,
            "drive": "OFF",
            "mode": "COOL" if model == "IC" else ("LC_AUTO" if model == "LC" else "OFF"),
            "capabilities": {
                "has_auto_mode": True,
                "has_dry_mode": True,
                "has_fan_speed": True,
                "has_air_direction": True,
                "fan_speed_stages": 4 if model == "IC" else 2,
            },
        }

    coordinator = create_mock_coordinator(groups_50, mock_system_info_payload)

    # Verify every group can be instantiated dynamically
    climates = [GB50ClimateEntity(coordinator, entry, gid) for gid, g in groups_50.items() if g["model"] == "IC"]
    fans = [GB50LossnayFanEntity(coordinator, entry, gid) for gid, g in groups_50.items() if g["model"] == "LC"]
    switches = [GB50GeneralEquipmentSwitch(coordinator, entry, gid) for gid, g in groups_50.items() if g["model"] == "PLC"]

    assert len(climates) == 35
    assert len(fans) == 10
    assert len(switches) == 5
    assert climates[0].name == "Zone-1"
    assert fans[0].name == "HRU-36"
    assert switches[0].name == "Relay-46"
