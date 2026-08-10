# turzi Bridge for Home Assistant

<p align="center">
  <img src="https://raw.githubusercontent.com/turzi-org/turzi-bridge-for-home-assistant/main/assets/turzi-logo.png" alt="Turzi" width="120" />
</p>

<p align="center">
  The official Home Assistant connector for the <strong>Turzi Protocol</strong> — live state out, authorized commands in, full audit attribution.
</p>

<p align="center">
  <a href="https://github.com/turzi-org/turzi-bridge-for-home-assistant/releases"><img src="https://img.shields.io/github/v/release/turzi-org/turzi-bridge-for-home-assistant?style=flat-square" alt="Release"></a>
  <a href="https://www.home-assistant.io/"><img src="https://img.shields.io/badge/Home%20Assistant-2024.4.0%2B-blue?style=flat-square&logo=home-assistant" alt="HA Version"></a>
  <a href="https://hacs.xyz/"><img src="https://img.shields.io/badge/HACS-Custom-orange?style=flat-square" alt="HACS"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/turzi-org/turzi-bridge-for-home-assistant?style=flat-square" alt="License"></a>
</p>

---

## Overview

**turzi Bridge** connects a Home Assistant instance to the Turzi platform (or any Turzi Protocol consumer) over MQTT, implementing **Turzi Protocol v1.1** ([PROTOCOL.md](PROTOCOL.md)):

- **State out** — every exposed entity's state, retained, with domain attributes (including the capability data — mode lists, ranges — that lets remote UIs render exactly the controls each device supports) and **origin attribution**: each state change is classified as commanded (`turzi`, with its `command_id`), HA-UI (`core_user`), `automation`, or `physical` (wall button, remote). This is what makes a complete audit trail possible downstream.
- **Commands in** — incoming commands are validated, **deduplicated** by `command_id`, **expired** if delivered late (TTL with a local 300 s ceiling — a stale unlock must never execute), translated to HA service calls, and **acknowledged** (`executed` / `failed` with reason).
- **Availability** — a retained LWT topic announces online/offline instantly, including ungraceful disconnects. No polling, no heartbeats.
- **Catalog up (cloud mode)** — the bridge registers its entity inventory with the Turzi platform over HTTPS (never over MQTT — the catalog lists unexposed entities and must not be readable by house clients).

One instance serves one `house/{house_id}/` namespace. A "house" can be a single dwelling or an entire building — Turzi Cloud runs one bridge per community.

---

## Requirements

| Requirement | Version |
|---|---|
| Home Assistant | ≥ 2024.4.0 |
| MQTT broker | Turzi Cloud provisions one automatically; self-hosted mode works with any broker (Mosquitto, EMQX, …) |
| Python dependency | `aiomqtt >= 2.0.0` (installed automatically) |

---

## Installation

### Via HACS (Recommended)

1. Open **HACS** → **Integrations** → ⋮ menu → **Custom repositories**
2. Add `https://github.com/turzi-org/turzi-bridge-for-home-assistant` as a custom repository (category: **Integration**)
3. Find **turzi Bridge** in HACS and click **Download**
4. Restart Home Assistant

### Manual

1. Copy `custom_components/turzi_bridge/` into your HA `config/custom_components/` directory
2. Restart Home Assistant

---

## Setup

**Settings → Devices & Services → Add Integration → turzi Bridge.** The flow offers two modes:

### Connect to Turzi Cloud (enrollment token)

Paste the single-use enrollment code (`TRZ-XXXX-XXXX-XXXX`) generated in the Turzi Community Manager. The bridge provisions itself: it exchanges the token for its house id, its own broker credentials, and its API token — no broker details to type, no secrets to copy. It then connects, registers its catalog, and the Community Manager flips to "bridge online".

- The token is single-use and expires (48 h by default). If it was already used or expired, generate a new one in the Community Manager.
- The **API base URL** field only matters when enrolling against a self-hosted Turzi backend.
- If the platform later unlinks this bridge, a **repair issue** appears in HA prompting re-enrollment; the bridge stops reconnecting on its own.

### Self-hosted / manual broker

For fully local operation against your own broker — no Turzi platform involved:

| Field | Description | Default |
|---|---|---|
| **Broker hostname** | IP or hostname of your MQTT broker | — |
| **Port** | Broker port | `1883` |
| **Username / Password** | Optional MQTT authentication | — |
| **House ID** | Topic namespace (`house/{house_id}/…`) — unique per installation | — |
| **Use TLS** | TLS for the MQTT connection | `false` |

The connection is tested before the entry is created. Broker settings can be changed later via **Reconfigure** on the integration entry.

---

## Exposure & privacy

What gets published is decided **here, at the bridge**, in the integration's options flow (**Configure** on the integration entry) — no custom panels, no YAML:

| Setting | Effect |
|---|---|
| **Included domains** | ALL entities in these domains are published |
| **Manually exposed entities** | Individual entities published *in addition* to the included domains (e.g. one specific sensor) |
| **Automatically expose new entities** | New entities in included domains publish without further action |
| **Privacy blocklist (never expose)** | These entities are **never** published — overriding every other setting, in every mode, surviving re-enrollment |

Effective exposure = **included domains ∪ manually exposed − privacy blocklist**.

Cloud enrollment defaults to all controllable domains, deliberately excluding the noisy ones (`sensor`, `binary_sensor`, `automation`, `device_tracker`, `person`) so the platform's device list stays a device list rather than a telemetry feed — add specific sensors via *manually exposed entities* when they matter.

Changes apply immediately: entities leaving the exposed set get their retained state cleared (clients drop them in real time), entities entering it publish their current state.

---

## How it works on the wire

The full specification is [PROTOCOL.md](PROTOCOL.md) — payloads, semantics, and client guidance. The shape of it:

| Direction | Topic | Retain |
|---|---|---|
| Bridge → clients | `house/{id}/state/{domain}/{entity_slug}` | ✅ |
| Bridge → clients | `house/{id}/availability` | ✅ |
| Bridge → clients | `house/{id}/ack/{command_id}` | ❌ |
| Publisher → bridge | `house/{id}/command/{domain}/{entity_slug}` | ❌ |
| Platform → bridge | `house/{id}/config/exposure` | ✅ |
| Publisher → bridge | `house/{id}/app/command/reload` | ❌ |

Who may publish commands is **deployment policy**, not protocol: in Turzi Cloud, apps hold subscribe-only credentials and every command flows through the platform API (authenticated, authorized, audited) before reaching the broker; in self-hosted mode, clients publish directly. The bridge doesn't care — it executes any authorized command arriving on its command topics, enforcing expiry, the TTL ceiling, and deduplication either way.

On reconnect (exponential backoff, 5 s → 60 s cap) the bridge re-registers its availability LWT and re-publishes all exposed states; in cloud mode it also refreshes its catalog registration when the inventory changed.

---

## Supported domains

All selectable domains and their published attributes are specified in [PROTOCOL.md §2](PROTOCOL.md#2-domain-attribute-specification). Highlights:

| Domain | Key attributes |
|---|---|
| `light` | `brightness`, `color_mode`, `color_temp_kelvin`, `rgb_color`, `effect` |
| `climate` | `target_temperature`, `current_temperature`, `hvac_action`, `hvac_modes`, `min_temp`/`max_temp`, `preset_modes`, `fan_modes` |
| `cover` | `current_position`, `current_tilt_position`, `device_class` |
| `alarm_control_panel` | `open_sensors`, `delay`, `code_arm_required`, `code_format`, `changed_by` |
| `fan` | `percentage`, `preset_mode`, `direction`, `oscillating` |
| `media_player` | `volume_level`, `media_title`, `media_artist`, `source`, `source_list` |
| `lock` | *(state only: `locked`, `unlocked`, `locking`, `unlocking`, `jammed`)* |
| `vacuum` | `battery_level`, `fan_speed`, `fan_speed_list` |
| `humidifier` | `current_humidity`, `target_humidity`, `min_humidity`/`max_humidity` |
| `sensor` / `binary_sensor` | `unit_of_measurement`, `device_class` |
| `switch`, `scene`, `script`, `button`, `input_boolean` | *(state only)* |

---

## Troubleshooting

**Enrollment fails**
- `token_unknown` / `token_expired_or_used`: generate a fresh code in the Community Manager — codes are single-use and expire after 48 h.
- Verify the HA host can reach the Turzi API over HTTPS (and your custom base URL if self-hosted).

**Bridge shows offline in the Community Manager**
- Check HA logs (**Settings → System → Logs**, filter `turzi`) for MQTT connection errors.
- If credentials were rotated or the bridge unlinked platform-side, a repair issue in HA will say so — re-enroll from there.

**Entities not appearing in the app / Community Manager**
- Open the integration's **Configure** dialog: is the entity's domain included, or the entity manually exposed? Is it on the privacy blocklist?
- Remember cloud defaults exclude sensor-class domains — add specific sensors manually.
- In the Community Manager, a published device still needs to be **placed in a space** to be visible to residents.

**Commands not executing**
- Check the ack: `failed` with `expired` means the command arrived after its TTL — look at broker connectivity and clock sync (NTP) on the HA host.
- `entity_not_exposed`: the target isn't in the effective exposed set.
- Check HA logs for service-call errors; every executed command also appears in the HA Logbook with its actor metadata.

---

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for architecture notes, local setup, and how the pieces fit (`mqtt_bridge.py` data plane, `cloud.py` catalog sync, `enrollment.py` provisioning).

## Contributing

Pull requests and issues are welcome — including connectors for other platforms; the protocol is open by design. Please open an issue before large changes.

## License

This project is licensed under the terms of the [MIT License](LICENSE).
