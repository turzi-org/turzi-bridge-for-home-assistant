"""Constants for the Turzi App Connector integration."""

DOMAIN = "turzi_ha_app_connector"

# Config entry keys (stored in entry.data)
CONF_BROKER = "broker"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_HOUSE_ID = "house_id"
CONF_USE_TLS = "use_tls"

# Options entry keys (stored in entry.options)
CONF_INCLUDED_DOMAINS = "included_domains"
CONF_EXPOSED_ENTITIES = "exposed_entities"
CONF_AUTO_ADD_NEW = "auto_add_new"

# Default port
DEFAULT_PORT = 1883

# Defaults
DEFAULT_AUTO_ADD_NEW = True
DEFAULT_INCLUDED_DOMAINS = [
    "light",
    "switch",
    "climate",
    "cover",
    "fan",
    "alarm_control_panel",
    "lock",
    "group",
]

# Panel constants
PANEL_URL = "/api/turzi_ha_app_connector/panel"
PANEL_TITLE = "Turzi"
PANEL_ICON = "mdi:alpha-t-circle"
PANEL_NAME = "turzi-panel"
PANEL_FOLDER = "frontend"
PANEL_FILENAME = "turzi-panel.js"
CUSTOM_COMPONENTS = "custom_components"
INTEGRATION_FOLDER = "turzi_ha_app_connector"

# Dispatcher signal for live panel updates
SIGNAL_CONFIG_UPDATED = f"{DOMAIN}_config_updated"

# All selectable domains in the panel domain picker (auto-expose candidates).
# Keep this in sync with ALL_DOMAINS in frontend/turzi-panel.js.
SELECTABLE_DOMAINS = [
    "alarm_control_panel",
    "automation",
    "binary_sensor",
    "button",
    "camera",
    "climate",
    "cover",
    "device_tracker",
    "fan",
    "group",
    "humidifier",
    "input_boolean",
    "input_button",
    "input_number",
    "input_select",
    "light",
    "lock",
    "media_player",
    "number",
    "person",
    "remote",
    "scene",
    "script",
    "select",
    "sensor",
    "siren",
    "switch",
    "vacuum",
    "valve",
    "water_heater",
    "weather",
]

# Domain-specific attributes to extract from entity states.
# This is the single source of truth matching the Turzi Protocol specification.
# Keys map to HA state attribute names. Only non-null values are included in payloads.
DOMAIN_ATTRIBUTES: dict[str, list[str]] = {
    # --- Existing (locked) + enriched ---
    "cover": [
        "current_position",         # 🔒 existing
        "current_tilt_position",    # 🆕
        "device_class",             # 🆕
    ],
    "climate": [
        "target_temperature",       # 🔒 existing
        "current_temperature",      # 🔒 existing
        "hvac_action",              # 🔒 existing
        "fan_mode",                 # 🔒 existing
        "hvac_modes",               # 🆕
        "preset_mode",              # 🆕
        "preset_modes",             # 🆕
        "fan_modes",                # 🆕
        "swing_mode",               # 🆕
        "swing_modes",              # 🆕
        "min_temp",                 # 🆕
        "max_temp",                 # 🆕
        "target_temp_high",         # 🆕
        "target_temp_low",          # 🆕
    ],
    "alarm_control_panel": [
        "open_sensors",             # 🔒 existing
        "delay",                    # 🔒 existing
        "code_arm_required",        # 🆕
        "code_format",              # 🆕
        "changed_by",               # 🆕
    ],
    # --- New domains ---
    "light": [
        "brightness",
        "color_mode",
        "color_temp_kelvin",
        "rgb_color",
        "effect",
        "min_color_temp_kelvin",
        "max_color_temp_kelvin",
    ],
    "fan": [
        "percentage",
        "preset_mode",
        "direction",
        "oscillating",
    ],
    # lock: no attributes (state is sufficient)
    "media_player": [
        "volume_level",
        "is_volume_muted",
        "media_title",
        "media_artist",
        "media_album_name",
        "media_content_type",
        "source",
        "source_list",
        "media_duration",
        "media_position",
    ],
    "sensor": [
        "unit_of_measurement",
        "device_class",
    ],
    "binary_sensor": [
        "device_class",
    ],
    "vacuum": [
        "battery_level",
        "fan_speed",
        "fan_speed_list",
    ],
    "humidifier": [
        "current_humidity",
        "target_humidity",
        "min_humidity",
        "max_humidity",
        "mode",
        "available_modes",
    ],
    "water_heater": [
        "current_temperature",
        "target_temperature",
        "min_temp",
        "max_temp",
        "operation_mode",
        "operation_list",
    ],
    "valve": [
        "current_position",
    ],
    "camera": [
        "is_recording",
        "is_streaming",
        "frontend_stream_type",
    ],
    "weather": [
        "temperature",
        "humidity",
        "pressure",
        "wind_speed",
        "wind_bearing",
    ],
    "person": [
        "latitude",
        "longitude",
        "gps_accuracy",
        "source",
    ],
    "device_tracker": [
        "latitude",
        "longitude",
        "gps_accuracy",
        "source_type",
    ],
    "siren": [
        "available_tones",
    ],
    "remote": [
        "current_activity",
        "activity_list",
    ],
    "input_number": [
        "min",
        "max",
        "step",
        "mode",
    ],
    "input_select": [
        "options",
    ],
    "automation": [
        "last_triggered",
    ],
    # State-only domains (no attributes extracted):
    # switch, group, scene, script, button, input_boolean, input_button
}

# Alarm mode -> HA service action mapping
ALARM_MODE_MAP: dict[str, str] = {
    "armed_away": "alarm_arm_away",
    "armed_home": "alarm_arm_home",
    "armed_night": "alarm_arm_night",
    "armed_vacation": "alarm_arm_vacation",
    "armed_custom_bypass": "alarm_arm_custom_bypass",
    "disarmed": "alarm_disarm",
    "triggered": "alarm_trigger",
}
