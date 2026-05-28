# turzi Bridge for Home Assistant

<p align="center">
  <img src="https://raw.githubusercontent.com/turzi-org/turzi-bridge-for-home-assistant/main/assets/turzi-logo.png" alt="Turzi" width="120" />
</p>

<p align="center">
  A custom Home Assistant integration that bridges your smart home with the <strong>Turzi mobile app</strong> via MQTT.
</p>

<p align="center">
  <a href="https://github.com/turzi-org/turzi-bridge-for-home-assistant/releases"><img src="https://img.shields.io/github/v/release/turzi-org/turzi-bridge-for-home-assistant?style=flat-square" alt="Release"></a>
  <a href="https://www.home-assistant.io/"><img src="https://img.shields.io/badge/Home%20Assistant-2024.4.0%2B-blue?style=flat-square&logo=home-assistant" alt="HA Version"></a>
  <a href="https://hacs.xyz/"><img src="https://img.shields.io/badge/HACS-Custom-orange?style=flat-square" alt="HACS"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/turzi-org/turzi-bridge-for-home-assistant?style=flat-square" alt="License"></a>
</p>

---

## Overview

**turzi Bridge for Home Assistant** is the official HA bridge for the [Turzi Protocol](PROTOCOL.md). It connects your Home Assistant instance to the Turzi mobile app by maintaining a live MQTT bridge that:

- **Publishes** real-time entity state changes from HA to the app
- **Receives** commands from the app and calls the corresponding HA services
- **Responds** to heartbeat pings to confirm connectivity
- **Re-publishes** all entity states on demand (app reconnect or manual reload)
- **Cleans up** MQTT retained messages when entities are removed from the exposed set

All entity exposure is managed through a **custom sidebar panel** — no need to touch HA labels, the options flow, or YAML.

> The connector implements the **MQTT transport binding** of the Turzi Protocol. See [PROTOCOL.md](PROTOCOL.md) for the full specification.

---

## Requirements

| Requirement | Version |
|---|---|
| Home Assistant | ≥ 2024.4.0 |
| External MQTT broker | Any (Mosquitto, EMQX, HiveMQ, etc.) |
| Python dependency | `aiomqtt >= 2.0.0` (installed automatically) |

---

## Installation

### Via HACS (Recommended)

1. Open **HACS** → **Integrations** → ⋮ menu → **Custom repositories**
2. Add `https://github.com/turzi-org/turzi-bridge-for-home-assistant` as a custom repository (category: **Integration**)
3. Find **turzi Bridge** in HACS and click **Download**
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/turzi_bridge/` folder into your HA `config/custom_components/` directory
2. Restart Home Assistant

---

## Configuration

### Initial Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **turzi Bridge**
3. Fill in your MQTT broker details:

| Field | Description | Default |
|---|---|---|
| **Broker hostname** | IP address or hostname of your MQTT broker | — |
| **Port** | MQTT broker port | `1883` |
| **Username** | Optional MQTT authentication username | — |
| **Password** | Optional MQTT authentication password | — |
| **House ID** | Unique identifier for this home (used as the MQTT topic prefix) | — |
| **Use TLS** | Enable TLS encryption for the MQTT connection | `false` |

> The **House ID** is a free-form string (e.g., `my_house`, `apartment_4b`). All MQTT topics are scoped under `house/{house_id}/` — it must be unique per installation.

The integration tests the connection to the MQTT broker before saving. If the connection fails, an error is shown and no entry is created.

### Reconfiguration

To update broker settings after initial setup, go to **Settings → Devices & Services**, find the Turzi entry, and select **Reconfigure**.

---

## Turzi Panel

After setup, a **Turzi** entry (🅣 icon) appears in the HA sidebar. This is the primary UI for all entity management — there is no separate options flow for exposure settings.

The panel requires admin access and has two tabs: **Entities** and **Status**.

---

### Entities Tab

The Entities tab combines exposure management and domain settings in a single screen.

#### Exposure Settings (top section)

| Control | What it does |
|---|---|
| **Auto-expose new entities** toggle | When ON, newly discovered entities from included domains are automatically exposed |
| **Included domains** search box | Type to search and add domains whose entities should be auto-exposed |
| **Domain tags** (× to remove) | Currently included domains; click × to remove a domain |
| **Select all / Clear all** | Adds or removes all available domains at once |

> Changes to included domains and the auto-expose toggle **save automatically** after a 1-second debounce. Adding a domain immediately exposes all its existing entities.

#### Entity List

| Control | What it does |
|---|---|
| **Search bar** | Filter by entity name or entity ID |
| **Domain filter chips** | Narrow the list to a single domain (shows entity count) |
| **Row checkbox** (left) | Select entity for batch operations |
| **Toggle switch** (right) | Expose or exclude this entity individually |
| **Select all visible** | Select all entities matching the current search/filter |
| **Batch bar** | Appears when entities are selected — Expose / Exclude / Clear |

#### Status Badges

| Badge | Meaning |
|---|---|
| `Auto Exposed` (orange) | Exposed because its domain is in the included domains list |
| `Manually Exposed` (green) | Exposed explicitly, outside of any included domain |
| `User Excluded` (amber) | In an included domain, but manually switched off |
| *(no badge)* | Not exposed, and not in any included domain |

Toggling a switch takes effect immediately — the entity's MQTT state is published or cleared in real time without any restart.

---

### Status Tab

Shows the current state of the MQTT connection:

- **Connection status** — Connected / Reconnecting (animated) / Disconnected
- **Broker details** — host, port, TLS, house ID
- **Statistics** — how many entities are exposed and how many are currently published
- **Reconnect counter** — how many times the bridge has reconnected since startup
- **Timestamps** — last connected and last disconnected
- **Activity log** — last 50 events (connections, disconnections, commands received from the app), displayed in reverse-chronological order and **updated in real time** — no page reload needed

---

## App Integration Guide

If you are developing the Turzi mobile app or a custom client, follow these guidelines to ensure robust, real-time communication with the Home Assistant bridge.

### 1. Connection & Session
**Connect with a Clean Session (`clean_session=True`).** 
Because the HA bridge publishes all entity states as retained messages, a clean session ensures that upon connection, the app instantly receives exactly one snapshot of the absolute latest state for every exposed entity. Using `clean_session=False` will flood the app with a queue of outdated historical changes that occurred while the phone was locked.

### 2. Quality of Service (QoS) & Topics

All topics are prefixed with `house/{house_id}/`. To achieve exactly-once delivery for commands and ensure no live state updates are missed, the app's MQTT client MUST use the following QoS levels:

| Direction | Action | Topic | QoS | Retain | Purpose |
|---|---|---|---|---|---|
| HA → App | **Subscribe** | `house/{id}/state/#` | **1** | ✅ | Live entity state updates |
| HA → App | **Subscribe** | `house/{id}/app/state/heartbeat` | **0** | ❌ | Heartbeat pong |
| App → HA | **Publish** | `house/{id}/command/{domain}/{entity_slug}` | **2** | ❌ | Control command |
| App → HA | **Publish** | `house/{id}/app/command/heartbeat` | **0** | ❌ | Heartbeat ping |
| App → HA | **Publish** | `house/{id}/app/command/reload` | **1** | ❌ | Full state reload |

> *Note: For QoS 2 to work correctly on commands, both the publisher (App) and subscriber (HA bridge) must use QoS 2. If the app publishes at QoS 1, delivery will be downgraded to QoS 1.*

### 3. Handling State Updates (HA → App)

Subscribe to `house/{id}/state/#` immediately after connecting. The broker will instantly push the retained state for every exposed entity. 

**Payload format:**
```json
{
  "state": "on",
  "last_changed": "2024-01-15T14:30:00.000000+00:00",
  "timestamp": 1705325400,
  "attributes": {
    "brightness": 200,
    "color_temp_kelvin": 3500
  }
}
```
*   The `attributes` field is only included when at least one value is non-null.
*   **Entity Deletions:** If an entity is removed from the exposed list in HA, the bridge publishes an **empty payload** to its topic. The app should interpret an empty payload as an instruction to delete that entity from the UI.

### 4. Sending Commands (App → HA)

Send commands to the specific entity topic.

**Payload format:**
```json
{
  "command": "light.turn_on",
  "parameters": { "brightness": 255 },
  "metadata": {
    "user_name": "John Doe",
    "user_email": "john@example.com"
  }
}
```
*   The `command` field must contain the exact HA service (e.g., `light.turn_on`, `cover.set_cover_position`).
*   Idempotent commands (e.g., `turn_on`, `turn_off`) are strongly preferred over non-idempotent ones (e.g., `toggle`) to prevent unexpected behavior during network retries.
*   The `metadata` is recorded in the HA Logbook for auditing.

### 5. Heartbeats

To verify the bridge is actively running, the app can publish a ping. The bridge will respond immediately.
*   **Ping** (App publishes): `{ "state": "ping" }`
*   **Pong** (App receives): `{ "state": "pong", "timestamp": "2024-01-15T14:30:00Z" }`

---

## Reconnection Behaviour

The bridge reconnects automatically using **exponential backoff**:

| Attempt | Delay |
|---|---|
| 1st | 5 s |
| 2nd | 10 s |
| 3rd | 20 s |
| 4th | 40 s |
| 5th+ | 60 s (max) |

All exposed entity states are re-published on every successful reconnect.

---

## Supported Domains & Attributes

| Domain | Key Attributes |
|---|---|
| `light` | `brightness`, `color_mode`, `color_temp_kelvin`, `rgb_color`, `effect` |
| `climate` | `target_temperature`, `current_temperature`, `hvac_action`, `hvac_modes`, `fan_mode`, `preset_mode` |
| `cover` | `current_position`, `current_tilt_position`, `device_class` |
| `alarm_control_panel` | `open_sensors`, `delay`, `code_arm_required`, `code_format`, `changed_by` |
| `fan` | `percentage`, `preset_mode`, `direction`, `oscillating` |
| `media_player` | `volume_level`, `is_volume_muted`, `media_title`, `media_artist`, `source` |
| `sensor` | `unit_of_measurement`, `device_class` |
| `binary_sensor` | `device_class` |
| `lock` | *(state only)* |
| `vacuum` | `battery_level`, `fan_speed` |
| `camera` | `is_recording`, `is_streaming` |
| `weather` | `temperature`, `humidity`, `pressure`, `wind_speed` |
| `person` / `device_tracker` | `latitude`, `longitude`, `gps_accuracy` |
| `switch`, `group`, `scene`, `script`, `button`, `input_boolean` | *(state only)* |

---

## Troubleshooting

### Cannot connect to MQTT broker

- Verify the broker is reachable from the HA host
- Double-check port, username, and password
- If using TLS, ensure the broker's certificate is trusted
- Check HA logs: **Settings → System → Logs**, filter by `turzi`
- Check the **Status tab** in the Turzi panel for connection events

### Entities not appearing in the app

- Open the Turzi panel → Entities tab and confirm the entity shows as **Auto Exposed** or **Manually Exposed**
- If the toggle is off, switch it on — MQTT publish is immediate
- Trigger a reload from the app or by publishing `{ "command": "reload" }` to `house/{id}/app/command/reload`

### Commands not executing

- Verify the topic format: `house/{house_id}/command/{domain}/{entity_slug}`
- Ensure the `command` field uses `{domain}.{action}` format (e.g., `light.turn_on`)
- Check HA logs for service call errors

---

## Protocol Reference

See **[PROTOCOL.md](PROTOCOL.md)** for the full message specification, topic schema, domain attribute definitions, and implementation guidelines.

---

## Contributing

Pull requests and issues are welcome. Please open an issue before submitting large changes.

---

## License

This project is licensed under the terms of the [MIT License](LICENSE).
