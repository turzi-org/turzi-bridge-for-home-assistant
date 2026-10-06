"""Constants for the turzi Bridge integration."""

DOMAIN = "turzi_bridge"

# Turzi Protocol v1.1
PROTOCOL_VERSION = "1.1"
# Hard ceiling on accepted command TTLs. Local-only by design (PROTOCOL v1.1 §2):
# the last line of defense against delayed delivery must hold even against a
# compromised platform, so it is never remotely configurable.
DEFAULT_TTL_CEILING_SECONDS = 300
CLOCK_SKEW_TOLERANCE_SECONDS = 10

# Config entry keys (stored in entry.data)
CONF_BROKER = "broker"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_HOUSE_ID = "house_id"
CONF_USE_TLS = "use_tls"

# Cloud enrollment (BRIDGE_CLOUD_API.md) — absent on manual/self-hosted setups
CONF_MODE = "mode"  # "cloud" | "manual"
CONF_BRIDGE_TOKEN = "bridge_token"
CONF_API_BASE_URL = "api_base_url"
CONF_ENROLLMENT_TOKEN = "enrollment_key"
# `turzi.cloud` es infraestructura máquina-a-máquina (broker, relays, media);
# la API vive en `turzi.com`. `api.turzi.cloud` resuelve a OTRA máquina y
# contesta 404 en /api/v2: el default apuntaba a algo que no es esta API.
#
# OJO: cambiar esto NO migra a nadie. La URL se guarda POR INSTALACIÓN en el
# `.storage` de cada Home Assistant cuando se enrola, así que este valor sólo
# lo ve un enrolamiento nuevo. Para mover un bridge ya instalado hay que
# reconfigurarlo en su propio HA.
DEFAULT_CLOUD_API_BASE_URL = "https://api.dev.turzi.com/api/v2"

# What is published lives in the entry's SUBENTRIES, one per item, so Home
# Assistant lists them on the bridge's page with an add button per type and a
# delete action per row:
#   domain_filter  {"domain": "light"}                         every light
#                  {"domain": "binary_sensor",
#                   "device_classes": [...]}                    only those classes
#   entity_filter  {"entities": ["switch.bomba", ...]}         those entities
#   exclusion      {"entities": [...]}                         never published
# An entity is published when any filter matches it and no exclusion names it.
# See exposure.py and scope.py.
SUBENTRY_DOMAIN_FILTER = "domain_filter"
SUBENTRY_ENTITY_FILTER = "entity_filter"
SUBENTRY_EXCLUSION = "exclusion"
FILTER_DOMAIN = "domain"
FILTER_DEVICE_CLASSES = "device_classes"
FILTER_ENTITIES = "entities"

# Options entry keys (stored in entry.options)
#
# On: a new entity that matches a domain filter is published by itself. Off:
# domain filters cover only the entities in CONF_FILTER_SNAPSHOT, taken each
# time a filter is saved, so a new one waits for the next save. Entity filters
# name their entities and do not depend on it.
CONF_AUTO_ADD_NEW = "auto_add_new"
CONF_FILTER_SNAPSHOT = "filter_snapshot"
# Last applied remote exposure revision (cloud mode; PROTOCOL.md §5)
CONF_CONFIG_REVISION = "config_revision"

# Keys of the exposure model before subentries (entry version 2), read only by
# the migration that turns them into subentries (`async_migrate_entry`). The
# privacy blocklist was `never_expose`; it is now the exclusions.
LEGACY_INCLUDED_DOMAINS = "included_domains"
LEGACY_NEVER_EXPOSE = "never_expose"
LEGACY_EXPOSED_ENTITIES = "exposed_entities"
LEGACY_BINARY_SENSOR_CLASSES = "included_binary_sensor_classes"
LEGACY_DEFAULT_INCLUDED_DOMAINS = [
    "light",
    "switch",
    "climate",
    "cover",
    "fan",
    "alarm_control_panel",
    "lock",
    "group",
]

# Default port
DEFAULT_PORT = 1883

# Defaults
DEFAULT_AUTO_ADD_NEW = True

# Dispatcher signal for config updates (diagnostics/status consumers)
SIGNAL_CONFIG_UPDATED = f"{DOMAIN}_config_updated"

# The binary sensors a building's platform needs whatever else is published
# (Santiago, 2026-10-06; turzi-apps DEFERRED_WORK.md D54):
# - a door's contact, which is the only input of the platform's door-held-open
#   alert and of a door's state in the Community Manager: door, garage_door,
#   opening, window;
# - life safety, for the security console: smoke, gas, carbon_monoxide,
#   moisture.
# They change state rarely, and they are the same kind of information as the
# locks and alarm panels. motion and occupancy stay out: they change
# constantly and say the most about who is home.
DOOR_AND_SAFETY_CLASSES = [
    "door",
    "garage_door",
    "opening",
    "window",
    "smoke",
    "gas",
    "carbon_monoxide",
    "moisture",
]

# The domain filters a new installation starts with, in every mode (Santiago,
# 2026-10-06): the devices a building controls, plus the door and safety
# binary sensors. Not input_boolean or script: helpers and automations are the
# installer's plumbing, not devices, and they get in only by a filter someone
# adds.
DEFAULT_FILTERS: list[dict] = [
    {FILTER_DOMAIN: domain, FILTER_DEVICE_CLASSES: []}
    for domain in (
        "alarm_control_panel",
        "climate",
        "cover",
        "fan",
        "light",
        "lock",
        "siren",
        "switch",
    )
] + [{FILTER_DOMAIN: "binary_sensor", FILTER_DEVICE_CLASSES: list(DOOR_AND_SAFETY_CLASSES)}]

# Every binary_sensor device class Home Assistant defines
# (BinarySensorDeviceClass), offered first in a filter's class picker. Kept
# here rather than read from the enum so that this module stays free of Home
# Assistant imports. A class Home Assistant adds later can still be typed in.
SELECTABLE_BINARY_SENSOR_CLASSES = [
    "battery",
    "battery_charging",
    "carbon_monoxide",
    "cold",
    "connectivity",
    "door",
    "garage_door",
    "gas",
    "heat",
    "light",
    "lock",
    "moisture",
    "motion",
    "moving",
    "occupancy",
    "opening",
    "plug",
    "power",
    "presence",
    "problem",
    "running",
    "safety",
    "smoke",
    "sound",
    "tamper",
    "update",
    "vibration",
    "window",
]

# The domains a filter can name.
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
        "temperature",              # 🔒 existing (HA attr name; renamed to target_temperature in payload)
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

# Map HA attribute names → Turzi Protocol key names where they differ.
# Applied at publish time so payloads always use the protocol-defined field names.
HA_TO_PROTOCOL_KEY: dict[str, str] = {
    "temperature": "target_temperature",  # climate: HA uses 'temperature', protocol uses 'target_temperature'
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
