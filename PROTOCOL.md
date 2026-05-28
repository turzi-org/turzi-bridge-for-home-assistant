# Turzi Protocol Specification

**Version:** 1.0.0  
**Status:** Production  

The Turzi Protocol defines a standardized communication interface between the **Turzi mobile app** and any **smart home core** (Home Assistant, Hubitat, custom implementations). It is transport-agnostic — the protocol core defines what is communicated, while transport bindings define how messages travel.

---

## Table of Contents

1. [Protocol Core](#1-protocol-core)
   - [Design Principles](#design-principles)
   - [State Update Payload](#state-update-payload)
   - [Command Payload](#command-payload)
   - [Heartbeat](#heartbeat)
   - [State Reload](#state-reload)
   - [Entity Cleanup](#entity-cleanup)
2. [Domain Attribute Specification](#2-domain-attribute-specification)
3. [Transport Bindings](#3-transport-bindings)
   - [MQTT Binding](#mqtt-binding)

---

## 1. Protocol Core

### Design Principles

1. **Platform-agnostic domains** — Domain names (e.g., `light`, `climate`, `cover`) are abstract device categories, not tied to any specific smart home platform. Connector implementations map their platform's device types to these standard domains.

2. **Standardized attributes** — Each domain defines a fixed set of attributes. Connectors extract available attributes from their platform and include them in state payloads.

3. **Backward compatibility** — Once published, domain attributes are never removed or renamed. New attributes may be added in future versions.

4. **Minimal payloads** — Only non-null attribute values are included in messages. The Turzi app handles missing attributes gracefully.

### State Update Payload

Sent by the smart home core whenever an entity's state changes.

```json
{
  "state": "on",
  "last_changed": "2024-01-15T14:30:00.000Z",
  "timestamp": 1705325400,
  "attributes": {
    "brightness": 255,
    "color_mode": "color_temp"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `state` | string | ✅ | The current state value (e.g., `"on"`, `"off"`, `"heating"`, `"22.5"`) |
| `last_changed` | string | ✅ | ISO 8601 timestamp of when the state last changed |
| `timestamp` | integer | ✅ | Unix epoch in seconds when this message was produced |
| `attributes` | object | ❌ | Domain-specific attributes. Only present if the domain defines attributes AND at least one has a non-null value |

### Command Payload

Sent by the Turzi app to request an action on an entity.

```json
{
  "command": "light.turn_on",
  "parameters": {
    "brightness": 255
  },
  "metadata": {
    "user_name": "John Doe",
    "user_email": "john@example.com"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `command` | string | ✅ | Action in `{domain}.{action}` format |
| `parameters` | object | ❌ | Action-specific parameters |
| `metadata` | object | ✅ | Information about the user who triggered the command |
| `metadata.user_name` | string | ✅ | Display name of the user |
| `metadata.user_email` | string | ✅ | Email of the user |

#### Alarm Control Panel Command Mapping

For `alarm_control_panel` entities, the `parameters.alarm_mode` value determines the resolved command:

| `alarm_mode` | Resolved `command` |
|---|---|
| `armed_away` | `alarm_control_panel.alarm_arm_away` |
| `armed_home` | `alarm_control_panel.alarm_arm_home` |
| `armed_night` | `alarm_control_panel.alarm_arm_night` |
| `armed_vacation` | `alarm_control_panel.alarm_arm_vacation` |
| `armed_custom_bypass` | `alarm_control_panel.alarm_arm_custom_bypass` |
| `disarmed` | `alarm_control_panel.alarm_disarm` |
| `triggered` | `alarm_control_panel.alarm_trigger` |

When the alarm mode mapping is used, the original `parameters` object is discarded (alarm commands do not pass additional parameters).

### Heartbeat

The heartbeat mechanism allows the app to verify connectivity with the smart home core.

**Ping** (App → Core):
```json
{
  "state": "ping"
}
```

**Pong** (Core → App):
```json
{
  "state": "pong",
  "timestamp": "2024-01-15T14:30:00.000Z"
}
```

### State Reload

The app can request the smart home core to re-send the current state of **all exposed entities**. This is used when:
- The app first connects and needs a full snapshot
- The app recovers from a disconnection
- The user manually triggers a refresh in the app

The core MUST also publish all entity states on initial startup/connection.

**Reload Request** (App → Core):
```json
{
  "command": "reload"
}
```

The core responds by re-publishing state update messages for every exposed entity (using the standard state update payload with `retain=true` in MQTT).

### Entity Cleanup

When an entity is removed from the exposed set (e.g., user excludes it via configuration), the core MUST clear its retained state from the transport layer. This prevents the app from showing stale entities.

In MQTT, this is done by publishing an **empty payload** with `retain=true` to the entity's state topic, which removes the retained message from the broker.

---

## 2. Domain Attribute Specification

### `cover`

| Attribute | Type | Description |
|-----------|------|-------------|
| `current_position` | int (0-100) | Current position. 0 = closed, 100 = fully open |
| `current_tilt_position` | int (0-100) | Tilt position for venetian blinds |
| `device_class` | string | Device type: `blind`, `garage`, `shade`, `shutter`, `curtain`, `awning`, `door`, `gate`, `window` |

### `climate`

| Attribute | Type | Description |
|-----------|------|-------------|
| `target_temperature` | float | Target temperature setpoint |
| `current_temperature` | float | Current temperature reading |
| `hvac_action` | string | Current action: `heating`, `cooling`, `idle`, `off`, `drying`, `fan` |
| `fan_mode` | string | Current fan mode |
| `hvac_modes` | string[] | Available HVAC modes (e.g., `["heat", "cool", "auto", "off"]`) |
| `preset_mode` | string | Current preset: `eco`, `away`, `comfort`, `home`, `sleep`, etc. |
| `preset_modes` | string[] | Available preset modes |
| `fan_modes` | string[] | Available fan modes |
| `swing_mode` | string | Current swing mode |
| `swing_modes` | string[] | Available swing modes |
| `min_temp` | float | Minimum settable temperature |
| `max_temp` | float | Maximum settable temperature |
| `target_temp_high` | float | Upper bound for dual setpoint systems |
| `target_temp_low` | float | Lower bound for dual setpoint systems |

### `alarm_control_panel`

| Attribute | Type | Description |
|-----------|------|-------------|
| `open_sensors` | object/list | Sensors preventing arming |
| `delay` | int | Entry/exit delay in seconds |
| `code_arm_required` | bool | Whether a code is needed to arm the system |
| `code_format` | string | Code format: `number` or `text` |
| `changed_by` | string | Who or what last changed the alarm state |

### `light`

| Attribute | Type | Description |
|-----------|------|-------------|
| `brightness` | int (0-255) | Brightness level |
| `color_mode` | string | Active color mode: `color_temp`, `hs`, `rgb`, `xy`, `onoff`, `brightness`, `white`, `rgbw`, `rgbww` |
| `color_temp_kelvin` | int | Color temperature in Kelvin |
| `rgb_color` | int[3] | RGB color as `[R, G, B]`, each 0-255 |
| `effect` | string | Active effect name |
| `min_color_temp_kelvin` | int | Minimum supported color temperature |
| `max_color_temp_kelvin` | int | Maximum supported color temperature |

### `fan`

| Attribute | Type | Description |
|-----------|------|-------------|
| `percentage` | int (0-100) | Fan speed percentage |
| `preset_mode` | string | Current preset mode |
| `direction` | string | Rotation direction: `forward` or `reverse` |
| `oscillating` | bool | Whether oscillation is active |

### `lock`

No attributes. State values convey all information: `locked`, `unlocked`, `locking`, `unlocking`, `jammed`.

### `media_player`

| Attribute | Type | Description |
|-----------|------|-------------|
| `volume_level` | float (0.0-1.0) | Current volume level |
| `is_volume_muted` | bool | Whether volume is muted |
| `media_title` | string | Currently playing title |
| `media_artist` | string | Currently playing artist |
| `media_album_name` | string | Currently playing album |
| `media_content_type` | string | Content type: `music`, `tvshow`, `movie`, `video`, `playlist`, `image` |
| `source` | string | Current input source |
| `source_list` | string[] | Available input sources |
| `media_duration` | int | Total duration in seconds |
| `media_position` | int | Current playback position in seconds |

### `sensor`

| Attribute | Type | Description |
|-----------|------|-------------|
| `unit_of_measurement` | string | Unit: `°C`, `°F`, `%`, `W`, `kWh`, `lx`, etc. |
| `device_class` | string | Sensor type: `temperature`, `humidity`, `power`, `energy`, `illuminance`, `battery`, `voltage`, `current`, `pressure`, etc. |

### `binary_sensor`

| Attribute | Type | Description |
|-----------|------|-------------|
| `device_class` | string | Sensor type: `motion`, `door`, `window`, `smoke`, `moisture`, `gas`, `vibration`, `occupancy`, `plug`, `presence`, `safety`, `tamper` |

### `vacuum`

| Attribute | Type | Description |
|-----------|------|-------------|
| `battery_level` | int (0-100) | Battery percentage |
| `fan_speed` | string | Current fan speed setting |
| `fan_speed_list` | string[] | Available fan speed settings |

### `humidifier`

| Attribute | Type | Description |
|-----------|------|-------------|
| `current_humidity` | float | Current humidity reading |
| `target_humidity` | float | Target humidity setpoint |
| `min_humidity` | float | Minimum settable humidity |
| `max_humidity` | float | Maximum settable humidity |
| `mode` | string | Current operating mode |
| `available_modes` | string[] | Available operating modes |

### `water_heater`

| Attribute | Type | Description |
|-----------|------|-------------|
| `current_temperature` | float | Current water temperature |
| `target_temperature` | float | Target water temperature |
| `min_temp` | float | Minimum settable temperature |
| `max_temp` | float | Maximum settable temperature |
| `operation_mode` | string | Current operation mode |
| `operation_list` | string[] | Available operation modes |

### `valve`

| Attribute | Type | Description |
|-----------|------|-------------|
| `current_position` | int (0-100) | Current position. 0 = closed, 100 = fully open |

### `camera`

| Attribute | Type | Description |
|-----------|------|-------------|
| `is_recording` | bool | Whether the camera is currently recording |
| `is_streaming` | bool | Whether the camera is currently streaming |
| `frontend_stream_type` | string | Stream type identifier |

*Note: Video streams are not transmitted through the Turzi Protocol. Only metadata is shared.*

### `weather`

| Attribute | Type | Description |
|-----------|------|-------------|
| `temperature` | float | Current temperature |
| `humidity` | float | Current humidity percentage |
| `pressure` | float | Atmospheric pressure |
| `wind_speed` | float | Wind speed |
| `wind_bearing` | float | Wind direction in degrees |

### `person` / `device_tracker`

| Attribute | Type | Description |
|-----------|------|-------------|
| `latitude` | float | GPS latitude |
| `longitude` | float | GPS longitude |
| `gps_accuracy` | int | GPS accuracy in meters |
| `source` / `source_type` | string | Tracking source identifier |

### `siren`

| Attribute | Type | Description |
|-----------|------|-------------|
| `available_tones` | string[] | Available tone options |

### `remote`

| Attribute | Type | Description |
|-----------|------|-------------|
| `current_activity` | string | Currently active activity |
| `activity_list` | string[] | Available activities |

### `input_number`

| Attribute | Type | Description |
|-----------|------|-------------|
| `min` | float | Minimum value |
| `max` | float | Maximum value |
| `step` | float | Step increment |
| `mode` | string | Input mode: `slider` or `box` |

### `input_select`

| Attribute | Type | Description |
|-----------|------|-------------|
| `options` | string[] | Available options |

### `automation`

| Attribute | Type | Description |
|-----------|------|-------------|
| `last_triggered` | string | ISO 8601 timestamp of last trigger |

### State-only Domains

The following domains transmit only `state`, `last_changed`, and `timestamp` — no additional attributes:

`switch`, `group`, `scene`, `script`, `button`, `input_boolean`, `input_button`

---

## 3. Transport Bindings

### MQTT Binding

The MQTT binding maps Turzi Protocol messages to MQTT topics and settings.

#### Topic Structure

All topics are prefixed with `house/{house_id}/`, where `house_id` is a unique identifier for the smart home instance.

| Direction | Topic Pattern | QoS | Retain | Message Type |
|-----------|---------------|-----|--------|-------------|
| Core → App | `house/{id}/state/{domain}/{entity_slug}` | 1 | ✅ | State Update |
| Core → App | `house/{id}/app/state/heartbeat` | 0 | ❌ | Heartbeat Pong |
| App → Core | `house/{id}/app/command/heartbeat` | 0 | ❌ | Heartbeat Ping |
| App → Core | `house/{id}/app/command/reload` | 1 | ❌ | State Reload Request |
| App → Core | `house/{id}/command/{domain}/{entity_slug}` | 2 | ❌ | Command |

- `{domain}` — The entity domain (e.g., `light`, `climate`, `cover`)
- `{entity_slug}` — The entity identifier without the domain prefix (e.g., for `light.living_room`, the slug is `living_room`)

#### Connection Requirements

| Parameter | Value |
|-----------|-------|
| Protocol | MQTT v3.1.1 (v4) or v5 |
| Keepalive | 60 seconds |
| Clean session | Yes |
| TLS | Optional (recommended for production) |
| Authentication | Optional username/password |

#### Reconnection Strategy

Connectors SHOULD implement automatic reconnection with exponential backoff:

| Attempt | Delay |
|---------|-------|
| 1 | 5 seconds |
| 2 | 10 seconds |
| 3 | 20 seconds |
| 4 | 40 seconds |
| 5+ | 60 seconds (max) |

#### Payload Encoding

All payloads are JSON-encoded UTF-8 strings.

---

## Implementing a Connector

To build a connector for your smart home platform:

1. **Map your platform's device types** to the Turzi Protocol domains listed above.
2. **Subscribe to command topics** (`house/{id}/command/#`) and translate incoming commands to your platform's service calls.
3. **Publish state updates** whenever an entity's state changes, using the standardized payload format with domain-specific attributes.
4. **Publish all states on connect** — on initial connection, publish the current state of every exposed entity.
5. **Implement heartbeat** — respond to pings with pongs.
6. **Handle reload requests** — when the app requests a reload, re-publish all exposed entity states.
7. **Clean up removed entities** — when an entity is no longer exposed, clear its retained state from the transport layer.

### Reference Implementations

- **Home Assistant**: [`turzi_app_connector`](https://github.com/turzi-org/turzi-home-assistant-integrations) — Custom integration using `aiomqtt`
