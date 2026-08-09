# Turzi Protocol Specification

**Version:** 1.1.0
**Status:** Production

> **v1.1 (2026-08-08)** adds — all additively (a v1.0 core remains valid; consumers must tolerate the absence of every v1.1 feature): availability (LWT), command identifiers with TTL/expiry, command acknowledgments, origin attribution on state updates, the exposure-configuration topic, and the deployment-modes appendix. The v1.0 heartbeat is deprecated in favor of availability.

The Turzi Protocol defines a standardized communication interface between the **Turzi mobile app** and any **smart home core** (Home Assistant, Hubitat, custom implementations). It is transport-agnostic — the protocol core defines what is communicated, while transport bindings define how messages travel.

---

## Table of Contents

1. [Protocol Core](#1-protocol-core)
   - [Design Principles](#design-principles)
   - [State Update Payload](#state-update-payload)
   - [Origin Attribution](#origin-attribution)
   - [Command Payload](#command-payload)
   - [Command Acknowledgment](#command-acknowledgment)
   - [Availability](#availability)
   - [Heartbeat (deprecated)](#heartbeat-deprecated)
   - [State Reload](#state-reload)
   - [Entity Cleanup](#entity-cleanup)
   - [Exposure Configuration](#exposure-configuration)
2. [Domain Attribute Specification](#2-domain-attribute-specification)
3. [Transport Bindings](#3-transport-bindings)
   - [MQTT Binding](#mqtt-binding)
4. [Deployment Modes and Publish Policy](#4-deployment-modes-and-publish-policy)

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
  },
  "origin": {
    "type": "physical",
    "command_id": null
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `state` | string | ✅ | The current state value (e.g., `"on"`, `"off"`, `"heating"`, `"22.5"`) |
| `last_changed` | string | ✅ | ISO 8601 timestamp of when the state last changed |
| `timestamp` | integer | ✅ | Unix epoch in seconds when this message was produced |
| `attributes` | object | ❌ | Domain-specific attributes. Only present if the domain defines attributes AND at least one has a non-null value |
| `origin` | object | ❌ *(v1.1)* | What caused this state change — see [Origin Attribution](#origin-attribution) |

### Origin Attribution

*(v1.1)* The OPTIONAL `origin` field classifies what caused a state change. This is the foundation for complete audit logging: actuations that never pass through the protocol (physical buttons, RF remotes, core automations) are visible *only* as state changes, and `origin` classifies them.

| `origin.type` | Meaning |
|---|---|
| `turzi` | Caused by a Turzi Protocol command; `command_id` SHOULD be set when the command carried one |
| `core_user` | Caused by a user acting directly on the smart home core (e.g. the Home Assistant UI) |
| `automation` | Caused by an automation/script/scene inside the core |
| `physical` | Originated at the device itself: wall button, remote control, manual operation |
| `unknown` | The core cannot classify the cause |

**Mapping guidance for Home Assistant connectors:** a state change whose context has a `parent_id` → `automation`; a `user_id` → `core_user` (or `turzi` if the connector's own service call produced it — connectors SHOULD track the context ids of calls they make and tag those changes `turzi` with the originating `command_id`); neither → `physical`.

Consumers MUST tolerate a missing `origin` (v1.0 cores) and treat it as `unknown`.

### Command Payload

Sent by the Turzi app to request an action on an entity.

```json
{
  "command": "light.turn_on",
  "command_id": "018f3c1e-7d2a-7bb8-9d3e-5a1f2b3c4d5e",
  "issued_at": 1705325400,
  "ttl_seconds": 60,
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
| `command_id` | string (UUID) | ❌ *(v1.1, RECOMMENDED)* | Publisher-generated unique identifier for this command instance |
| `issued_at` | integer (epoch s) | ❌ *(v1.1, RECOMMENDED)* | When the actor triggered the command |
| `ttl_seconds` | integer | ❌ *(v1.1)* | Validity window from `issued_at`. Suggested defaults: 30 for actuation domains (`lock`, `cover`, `alarm_control_panel`), 60 otherwise |
| `parameters` | object | ❌ | Action-specific parameters |
| `metadata` | object | ✅ | Information about the user who triggered the command |
| `metadata.user_name` | string | ✅ | Display name of the user |
| `metadata.user_email` | string | ✅ | Email of the user |

#### Command Expiry *(v1.1)*

A command delivered late — broker queuing, in-flight QoS handshakes completing after a reconnect, upstream retries, congested links — no longer represents the actor's intent; executing an unlock minutes after the tap is a security incident, not reliability. Therefore: cores MUST discard a command received after `issued_at + ttl_seconds` and, when it carries a `command_id`, ack it `failed` with reason `expired`. Cores SHOULD tolerate modest clock skew (suggest ±10 s) and rely on NTP-disciplined clocks. Commands without `issued_at` are executed as in v1.0 (no expiry check).

**TTL ceiling.** Because the publisher chooses `ttl_seconds`, a compromised or misconfigured publisher could nullify expiry with an arbitrarily large value. Cores MUST therefore clamp the effective TTL to a locally configured maximum (default: 300 s) — a command whose requested TTL exceeds the ceiling is evaluated against the ceiling, not rejected. The ceiling is configurable only on the core itself, never remotely. Which TTL a publisher *requests* per domain is publisher-side policy and intentionally outside this specification.

#### Command Deduplication *(v1.1)*

Cores MUST treat a repeated `command_id` as a duplicate delivery and execute it at most once. The dedupe retention window MUST be at least the core's TTL ceiling — a shorter window would let a late duplicate pass both dedupe and expiry and actuate twice. This permits publishers to use QoS 1 on reliable links without risking double actuation. Commands without a `command_id` are executed as in v1.0 (no ack, no dedupe).

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

### Command Acknowledgment

*(v1.1)* When a command carries a `command_id`, the core MUST publish exactly one terminal acknowledgment to the command's ack address (in MQTT: `house/{id}/ack/{command_id}`, QoS 1, not retained).

```json
{
  "command_id": "018f3c1e-7d2a-7bb8-9d3e-5a1f2b3c4d5e",
  "status": "executed",
  "reason": null,
  "timestamp": 1705325401
}
```

| `status` | Meaning |
|---|---|
| `received` | OPTIONAL, non-terminal: command parsed and accepted for execution |
| `executed` | Terminal: the underlying platform action was invoked successfully |
| `failed` | Terminal: the command was not executed — `reason` MUST explain why |

`reason` values are free-form but SHOULD use these well-known values where applicable: `entity_unavailable`, `entity_not_exposed`, `unsupported_command`, `invalid_parameters`, `platform_error`, `expired`.

**Client interpretation** (normative guidance):

| Observation | Meaning | Suggested UI |
|---|---|---|
| `executed`, then state update | Confirmed, state changed | Show new state |
| `executed`, no state update | Command was a no-op (e.g. unlocking an unlocked door) | Resolve as success |
| `failed` | Rejected — reason available | Show error immediately |
| Nothing within timeout (suggest 5 s) | Command or core lost | Check availability; show "home unreachable" if offline |

The ack reports *invocation*, not physical outcome. Observed physical outcome remains the state stream's job; the two are correlated via `origin.command_id`.

### Availability

*(v1.1)* The core advertises its own liveness on a retained topic using the transport's disconnect-detection mechanism (MQTT Last Will and Testament). This supersedes the heartbeat, which required active polling and could not detect an ungraceful disconnect promptly.

**Payload (online):**
```json
{
  "state": "online",
  "timestamp": 1705325400,
  "protocol_version": "1.1",
  "config_revision": 42
}
```

**Payload (offline):**
```json
{
  "state": "offline",
  "reason": "shutdown"
}
```

- The core MUST register an LWT on connect with payload `{"state": "offline", "reason": "connection_lost"}` (retained, QoS 1) so the broker announces death on its behalf.
- The core MUST publish the `online` payload immediately after connecting, and SHOULD publish `{"state": "offline", "reason": "shutdown"}` before a graceful disconnect.
- `config_revision` reports the currently applied exposure configuration revision (see [Exposure Configuration](#exposure-configuration)). Cores that do not support remote configuration omit it. Because the topic is retained, this doubles as the configuration acknowledgment.
- Clients MUST treat all entity state for the house as *unverified* (stale-but-displayable) while availability is `offline`, and SHOULD surface home connectivity in the UI.

### Heartbeat (deprecated)

> **Deprecated in v1.1** in favor of [Availability](#availability). Cores SHOULD continue answering pings for backward compatibility; clients SHOULD prefer the availability topic. The heartbeat will be removed in a future major version.

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

### Exposure Configuration

*(v1.1, optional capability)* Cores MAY support remote management of the exposed-entity set. Support is declared through the platform's catalog registration (see the Turzi Bridge Cloud API, a separate document — the catalog itself is intentionally **not** part of this protocol: it enumerates unexposed entities and therefore must not transit a topic readable by house clients).

**Topic:** `house/{id}/config/exposure` — QoS 1, **retained**, published by the **platform only**. Cores subscribe; clients have no business on this topic and deployments SHOULD deny them access to `house/{id}/config/#`.

```json
{
  "revision": 42,
  "updated_at": "2024-01-15T14:30:00.000Z",
  "entities": ["light.living_room", "lock.front_door", "cover.garage"],
  "auto_add_domains": ["light", "switch"]
}
```

- `revision` — monotonically increasing integer. Cores MUST ignore a payload whose revision is ≤ the currently applied one (retained replay protection).
- `entities` — the complete exposed set (full replacement, not a delta).
- `auto_add_domains` — domains whose newly discovered entities are exposed automatically without waiting for a new revision.

Core obligations on applying a revision:

1. **Persist locally**, so the configuration survives restarts and platform outages.
2. **Honor the local privacy blocklist**: entities locally marked "never expose" MUST be excluded even if listed — local exclusion always wins. The core reports effective exposure through catalog registration so the platform can display the discrepancy.
3. **Clean up removed entities**: for every entity leaving the exposed set, publish an empty retained payload to its state topic (see [Entity Cleanup](#entity-cleanup)).
4. **Publish current state** for every entity entering the exposed set.
5. **Acknowledge** by updating `config_revision` in the retained availability payload.

Cores that do not support remote configuration simply never subscribe to this topic; their exposure remains locally managed.

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
| Core → Clients | `house/{id}/state/{domain}/{entity_slug}` | 1 | ✅ | State Update |
| Core → Clients | `house/{id}/availability` | 1 | ✅ | Availability *(v1.1)* |
| Core → Clients | `house/{id}/ack/{command_id}` | 1 | ❌ | Command Acknowledgment *(v1.1)* |
| Publisher → Core | `house/{id}/command/{domain}/{entity_slug}` | 2 (1 with `command_id`) | ❌ | Command |
| Platform → Core | `house/{id}/config/exposure` | 1 | ✅ | Exposure Configuration *(v1.1)* |
| Publisher → Core | `house/{id}/app/command/reload` | 1 | ❌ | State Reload Request |
| Core → App | `house/{id}/app/state/heartbeat` *(deprecated)* | 0 | ❌ | Heartbeat Pong |
| App → Core | `house/{id}/app/command/heartbeat` *(deprecated)* | 0 | ❌ | Heartbeat Ping |

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

## 4. Deployment Modes and Publish Policy

*(v1.1)* The protocol defines message semantics; it deliberately does **not** define who may publish commands. That is a deployment policy:

**Managed platform (e.g. Turzi Cloud):** clients (mobile app, management web UIs) receive **strictly subscribe-only** broker credentials, covering `house/{id}/state/#`, `availability`, and `ack/#`. All client-initiated actions — commands *and* state reload — are submitted to the platform API, which authenticates, authorizes, and rate-limits the actor, then publishes to the corresponding topic (`command/{domain}/{entity_slug}` or `app/command/reload`) on the client's behalf, stamping verified identity into command `metadata`. Rate-limiting reload matters: it triggers a full state republish from the core, making it the one non-actuating topic with amplification potential. Only the platform holds publish rights on `command/#`, `config/#`, and `app/command/#`; only the core's per-house credential holds publish rights on `state/#`, `availability`, and `ack/#`.

**Self-hosted / local:** clients publish commands directly to the broker using credentials owned and managed by the operator. All protocol semantics — including `command_id`, acks, and origin — behave identically; there is simply no platform intermediary.

Connector implementations MUST NOT assume either mode: a compliant core executes any authorized command arriving on its command topics, regardless of who published it.

**Delayed-delivery requirements (both modes):**

- Cores MUST use a **clean session** (MQTT 3.1.1) or session expiry of 0 (MQTT 5) on their command-topic subscriptions. This is a security requirement, not a tuning default: a persistent session causes commands addressed to an offline house to queue at the broker and execute on reconnect, long after the actor's intent has lapsed. Command-topic delivery is intentionally *not* reliable across core downtime — command expiry and the platform's fail-fast are the compensating behaviors.
- Publishers on brokers supporting MQTT 5 SHOULD additionally set the Message Expiry Interval property to `ttl_seconds` so the broker itself drops stale commands.
- In managed mode, the platform SHOULD consult the retained `availability` topic before publishing a command and reject the request immediately (`home_offline`) when the house is offline. The platform MUST NOT retry a command past its expiry.

---

## Implementing a Connector

To build a connector for your smart home platform:

1. **Map your platform's device types** to the Turzi Protocol domains listed above.
2. **Subscribe to command topics** (`house/{id}/command/#`) with a clean session and translate incoming commands to your platform's service calls — enforcing command expiry, the TTL ceiling, and `command_id` deduplication.
3. **Acknowledge commands** — publish exactly one terminal ack per `command_id`.
4. **Publish state updates** whenever an entity's state changes, using the standardized payload format with domain-specific attributes and `origin` attribution.
5. **Publish availability** — register an LWT and publish the retained `online` payload on connect.
6. **Publish all states on connect** — on initial connection, publish the current state of every exposed entity.
7. **Handle reload requests** — when a reload is requested, re-publish all exposed entity states.
8. **Clean up removed entities** — when an entity is no longer exposed, clear its retained state from the transport layer.
9. *(Optional)* **Support remote exposure configuration** — subscribe to `config/exposure` and declare the capability through catalog registration.

### Reference Implementations

- **Home Assistant**: [`turzi_app_connector`](https://github.com/turzi-org/turzi-home-assistant-integrations) — Custom integration using `aiomqtt`
