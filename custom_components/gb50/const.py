"""Constants for the Mitsubishi GB-50 HVAC integration."""

from __future__ import annotations

DOMAIN = "gb50"
DEFAULT_PORT = 8080
DEFAULT_NAME = "Mitsubishi GB-50"

CONF_API_KEY = "api_key"
CONF_USE_SSL = "use_ssl"

# Signal templates for dynamic entity dispatch and runtime updates
SIGNAL_GROUP_UPDATED = "gb50_group_updated_{entry_id}_{group_id}"
SIGNAL_NEW_GROUP_DISCOVERED = "gb50_new_group_discovered_{entry_id}"
SIGNAL_SYSTEM_UPDATED = "gb50_system_updated_{entry_id}"

# Supported platforms
PLATFORMS = [
    "climate",
    "fan",
    "switch",
    "binary_sensor",
    "button",
    "sensor",
]

# Controller Model Types (matching GB-50 protocol definitions)
MODEL_IC = "IC"    # Indoor Air Conditioner Unit
MODEL_LC = "LC"    # LOSSNAY Heat Recovery Ventilator
MODEL_SC = "SC"    # System Controller
MODEL_RC = "RC"    # Remote Controller
MODEL_FU = "FU"    # Outdoor Fan Unit
MODEL_PLC = "PLC"  # Programmable Logic / General Equipment Relay
MODEL_MC = "MC"    # Measurement Controller

# Operation Modes
MODE_OFF = "OFF"
MODE_HEAT = "HEAT"
MODE_COOL = "COOL"
MODE_FAN = "FAN"
MODE_DRY = "DRY"
MODE_AUTO = "AUTO"
MODE_AUTOHEAT = "AUTOHEAT"
MODE_AUTOCOOL = "AUTOCOOL"

# LOSSNAY Specific Modes
MODE_LC_AUTO = "LC_AUTO"
MODE_BYPASS = "BYPASS"
MODE_HEATRECOVERY = "HEATRECOVERY"

# Fan Speeds
FAN_AUTO = "AUTO"
FAN_LOW = "LOW"
FAN_MID2 = "MID2"
FAN_MID1 = "MID1"
FAN_HIGH = "HIGH"

# Air Directions / Swing Louver
AIR_DIR_AUTO = "AUTO"
AIR_DIR_HORIZONTAL = "HORIZONTAL"
AIR_DIR_MID1 = "MID1"
AIR_DIR_MID2 = "MID2"
AIR_DIR_VERTICAL = "VERTICAL"
AIR_DIR_SWING = "SWING"
