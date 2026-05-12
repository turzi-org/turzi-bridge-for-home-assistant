# Turzi HA App Connector

<p align="center">
  <img src="assets/logo-turzi-square.png" alt="Turzi Logo" width="120" />
</p>

<p align="center">
  A custom Home Assistant integration that bridges your smart home with the <strong>Turzi mobile app</strong> via MQTT.
</p>

<p align="center">
  <a href="https://github.com/turzi-org/turzi_ha_app_connector/releases"><img src="https://img.shields.io/github/v/release/turzi-org/turzi_ha_app_connector?style=flat-square" alt="Release"></a>
  <a href="https://www.home-assistant.io/"><img src="https://img.shields.io/badge/Home%20Assistant-2024.1.0%2B-blue?style=flat-square&logo=home-assistant" alt="HA Version"></a>
  <a href="https://hacs.xyz/"><img src="https://img.shields.io/badge/HACS-Custom-orange?style=flat-square" alt="HACS"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/turzi-org/turzi_ha_app_connector?style=flat-square" alt="License"></a>
</p>

---

## Overview

**turzi_ha_app_connector** is the official Home Assistant connector for the [Turzi Protocol](PROTOCOL.md). It connects your Home Assistant instance to the Turzi mobile app by maintaining a live MQTT bridge that:

- **Publishes** real-time entity state changes from HA to the app
- **Receives** commands from the app and calls the corresponding HA services
- **Responds** to heartbeat pings to confirm connectivity
- **Re-publishes** all entity states on demand (app reconnect or manual reload)
- **Cleans up** MQTT retained messages when entities are removed from the exposed set

> The connector implements the **MQTT transport binding** of the Turzi Protocol. See [PROTOCOL.md](PROTOCOL.md) for the full specification.

---

## Requirements

| Requirement | Version |
|---|---|
| Home Assistant | ≥ 2024.1.0 |
| External MQTT broker | Any (Mosquitto, EMQX, HiveMQ, etc.) |
| Python dependency | `aiomqtt >= 2.0.0` (installed automatically) |

---

## Installation

### Via HACS (Recommended)

1. Open **HACS** → **Integrations** → ⋮ menu → **Custom repositories**
2. Add `https://github.com/turzi-org/turzi_ha_app_connector` as a custom repository (category: **Integration**)
3. Find **Turzi HA App Connector** in HACS and click **Download**
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/turzi_ha_app_connector/` folder into your HA `config/custom_components/` directory
2. Restart Home Assistant

---

## Configuration

### Initial Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Turzi HA App Connector**
3. Fill in your MQTT broker details:

| Field | Description | Default |
|---|---|---|
| **Broker hostname** | IP address or hostname of your MQTT broker | — |
| **Port** | MQTT broker port | `1883` |
| **Username** | Optional MQTT authentication username | — |
| **Password** | Optional MQTT authentication password | — |
| **House ID** | Unique identifier for this home (used as the MQTT topic prefix) | — |
| **Use TLS** | Enable TLS encryption for the MQTT connection | `false` |

> The **House ID** is a free-form string (e.g., `my_house`, `apartment_4b`). All MQTT topics will be scoped under `house/{house_id}/`, so it must be unique per installation.

The integration tests the connection to the MQTT broker before saving. If the connection fails, an error will be shown and no entry will be created.

### Reconfiguration

To update broker settings after initial setup, go to **Settings → Devices & Services**, find the integration entry, and select **Reconfigure**.

---

## Entity Management Panel

After setup, a **Turzi** entry appears in the HA sidebar. This is the primary UI for all entity and label configuration — there is no options flow for entity settings.

The panel requires admin access and has two tabs.

---

### Entities tab

A searchable, filterable list of every entity in your HA instance.

| Control | What it does |
|---|---|
| **Search bar** | Filter by entity name or entity ID |
| **Domain chips** | Narrow the list to a single domain |
| **Toggle switch** | Add or remove the expose label from that entity |

**Entity badges:**

| Badge | Meaning |
|---|---|
| `auto` | Labeled automatically by the integration (domain rule match) |
| `manual` | Label was added manually by you |
| `additional` | Entity is in the additional entities list |

Toggling a switch takes effect immediately — the entity's MQTT state is published or cleared in real time without any restart.

---

### Settings tab

| Field | Description |
|---|---|
| **Expose label** | The HA label applied to exposed entities (lowercase, e.g. `turzi`). Leave empty to disable label management. |
| **Label management mode** | How the integration manages labels (see below). |
| **Included domains** | Entities from these domains are labeled when rules run. |

#### Label management modes

| Mode | What happens on save | New entities | Domain rules change |
|---|---|---|---|
| **Seed** *(default)* | Labels applied once to all matching entities. Future additions are manual. | ❌ Manual | Re-seeds (add-only) |
| **Automatic** | Labels fully synced with domain rules at all times. | ✅ Auto-labeled | ✅ Labels added & removed |
| **Mixed** | Same as Automatic, but labels you applied manually are never auto-removed. | ✅ Auto-labeled (domain matches) | ✅ Removes auto-labeled only |

> **Default included domains:** `light`, `switch`, `climate`, `cover`, `fan`, `alarm_control_panel`, `lock`, `group`

---

### How exposure is determined at runtime

```
1. Entity has the expose label      → exposed  (always wins)
2. Entity is in additional_entities → exposed  (safety-net)
3. Otherwise                        → not exposed
```

Domain rules are only used to decide which entities receive the label — they are not evaluated at runtime.

---

### Live sync

Changes take effect immediately without restarting HA:

- **Toggle on** in panel → label added → state published to MQTT
- **Toggle off** in panel → label removed → retained MQTT message cleared
- **New entity registered** in HA (Automatic/Mixed only) → auto-labeled and published if it matches domain rules
- **Settings saved** → label sweep runs, MQTT state synced across all affected entities

---


## MQTT Topic Structure

All topics are prefixed with `house/{house_id}/`.

| Direction | Topic | QoS | Retain | Purpose |
|---|---|---|---|---|
| HA → App | `house/{id}/state/{domain}/{entity_slug}` | 1 | ✅ | Entity state update |
| HA → App | `house/{id}/app/state/heartbeat` | 1 | ❌ | Heartbeat pong |
| App → HA | `house/{id}/command/{domain}/{entity_slug}` | 0 | ❌ | Control command |
| App → HA | `house/{id}/app/command/heartbeat` | 1 | ❌ | Heartbeat ping |
| App → HA | `house/{id}/app/command/reload` | 1 | ❌ | Full state reload |

**Example topics** for `house_id = my_house`:

```
house/my_house/state/light/living_room
house/my_house/state/climate/main_thermostat
house/my_house/command/light/living_room
house/my_house/app/command/heartbeat
house/my_house/app/command/reload
```

---

## Payload Formats

### State Update (HA → App)

Published whenever an entity's state changes, and on initial connect / reload.

```json
{
  "state": "on",
  "last_changed": "2024-01-15T14:30:00.000000+00:00",
  "timestamp": 1705325400,
  "attributes": {
    "brightness": 200,
    "color_mode": "color_temp",
    "color_temp_kelvin": 3500
  }
}
```

The `attributes` field is only present when the domain defines attributes and at least one has a non-null value.

### Command (App → HA)

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

Every command is logged to the HA **Logbook** with the user name and action for auditability.

### Heartbeat

**Ping** (App → HA): `{ "state": "ping" }`

**Pong** (HA → App): `{ "state": "pong", "timestamp": "2024-01-15T14:30:00.000000+00:00" }`

### Reload Request

**App → HA**: `{ "command": "reload" }`

The integration re-publishes all currently exposed entity states with `retain=true`.

---

## Manual Reload via Helper

You can also trigger a full state reload from within HA (e.g., from an automation or dashboard) by toggling an `input_boolean` helper:

```yaml
# configuration.yaml
input_boolean:
  app_reload_house_structure:
    name: "Reload Turzi App Structure"
    icon: mdi:refresh
```

Turning `input_boolean.app_reload_house_structure` **on** will cause the bridge to re-publish all exposed entity states to MQTT.

---

## Reconnection Behaviour

The bridge automatically reconnects to the MQTT broker using **exponential backoff**:

| Attempt | Delay |
|---|---|
| 1st | 5 s |
| 2nd | 10 s |
| 3rd | 20 s |
| 4th | 40 s |
| 5th+ | 60 s (max) |

On reconnect, all exposed entity states are re-published automatically.

---

## Supported Domains & Attributes

The following table summarises the attributes published per domain. See [PROTOCOL.md](PROTOCOL.md) for the full attribute specification.

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
| `switch`, `group`, `scene`, `script`, `button`, `input_boolean`, `input_button` | *(state only)* |

---

## Troubleshooting

### Cannot connect to MQTT broker

- Verify the broker is reachable from the HA host (`ping <broker>`)
- Double-check port, username, and password
- If using TLS, make sure your broker's certificate is trusted
- Check the HA logs: **Settings → System → Logs**, filter by `turzi`

### Entities not appearing in the app

- Confirm the entity's domain is selected in the Options flow
- Check that the entity is not in the **Excluded entities** list
- Trigger a reload via `input_boolean.app_reload_house_structure` or the app's refresh action

### Commands not executing

- Verify the MQTT topic format matches `house/{house_id}/command/{domain}/{entity_slug}`
- Ensure the `command` field uses `{domain}.{action}` format (e.g., `light.turn_on`)
- Check HA logs for errors related to service calls

---

## Protocol Reference

For the full message specification, topic schema, domain attribute definitions, and implementation guidelines, see **[PROTOCOL.md](PROTOCOL.md)**.

---

## Contributing

Pull requests and issues are welcome. Please open an issue before submitting large changes.

---

## License

This project is licensed under the terms of the [MIT License](LICENSE).
