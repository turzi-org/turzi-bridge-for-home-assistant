# turzi Bridge — Development Guide

> **Purpose:** handoff guide for developers (and AI agents) picking up this project: current architecture, design decisions and their reasons, file structure, and data flow. The wire format is specified in [PROTOCOL.md](PROTOCOL.md) (Turzi Protocol v1.1) — this document covers how *this* connector implements it.

**Repo:** `https://github.com/turzi-org/turzi-bridge-for-home-assistant`
**Integration path:** `custom_components/turzi_bridge/`
**HA domain:** `turzi_bridge`

---

## Architecture Overview

```
Home Assistant
│
├── config_entry (one per house/community)
│   ├── data: mode ("cloud" | "manual")
│   │   ├── cloud:  api_base_url, bridge_token, house_id, mqtt credentials (all provisioned)
│   │   └── manual: broker, port, username, password, house_id, use_tls (typed by operator)
│   └── options: included_domains[], exposed_entities[], auto_add_new, never_expose[]
│
├── TurziMqttBridge            mqtt_bridge.py   (the data plane)
│   ├── aiomqtt connection, exponential backoff, clean session
│   ├── Availability: LWT registration + retained online payload (with config_revision)
│   ├── State out: retained per-entity payloads with domain attributes + origin attribution
│   ├── Commands in: expiry check (TTL ceiling), command_id dedupe, HA service call, ack
│   ├── config/exposure subscribe (remote_config capability, revision-guarded)
│   └── Entity cleanup: empty retained payload when an entity leaves the exposed set
│
├── TurziCloudSync             cloud.py         (cloud mode only)
│   ├── POST /catalog on startup + registry changes (debounced) — full candidate catalog
│   ├── Refreshes bridge/core versions with every registration
│   └── 401 token_revoked → repair issue prompting re-enrollment, bridge stops
│
├── Enrollment                 enrollment.py    (cloud mode only)
│   └── POST /enroll: exchanges the TRZ- token for house_id + bridge_token + MQTT credential
│
└── Config flow                config_flow.py
    ├── Menu: cloud (token) | manual (broker form) — plus reconfigure
    └── Options flow: exposure & privacy (see Data Model)
```

There is **no custom panel, no WebSocket/REST API, no bundled frontend** — earlier versions had a sidebar panel; it was deleted when exposure management moved to the native options flow and (for the platform-facing parts) to the Turzi Community Manager. If you find references to `panel.py`, `websockets.py` or `frontend/`, they are historical.

---

## File Structure

```
custom_components/turzi_bridge/
├── __init__.py           Setup/teardown; wires bridge + cloud sync per entry
├── config_flow.py        Menu flow (cloud/manual), reconfigure, options flow
├── const.py              CONF keys, SELECTABLE_DOMAINS, NOISY_DOMAINS,
│                         DOMAIN_ATTRIBUTES (+ HA→protocol key renames),
│                         DEFAULT_TTL_CEILING_SECONDS (300, local-only by design)
├── enrollment.py         Cloud enrollment client (EnrollResult, EnrollmentError)
├── cloud.py              build_catalog() + TurziCloudSync
├── mqtt_bridge.py        TurziMqttBridge — the entire data plane
├── manifest.json         Integration metadata (aiomqtt dependency)
├── strings.json          UI strings (EN) · translations/en.json
└── brand/                logo + icon for the HA integrations page
```

---

## Data Model

### `config_entry.data` (identity & transport — changed via enrollment/reconfigure only)

Cloud mode stores what enrollment returned (`api_base_url`, `bridge_token`, `house_id`, MQTT host/port/TLS/credentials); manual mode stores the operator-typed broker details. `mode` discriminates.

### `config_entry.options` (exposure & privacy — mutable at runtime, no restart)

| Key | Type | Meaning |
|---|---|---|
| `included_domains` | list[str] | ALL entities of these domains are published |
| `exposed_entities` | list[str] | **Manual additions only** — entities published *in addition to* the included domains |
| `auto_add_new` | bool | Newly created entities in included domains publish automatically |
| `never_expose` | list[str] | Privacy blocklist — never published, overrides everything, survives re-enrollment |

**Effective exposure = included_domains ∪ exposed_entities − never_expose.** This is the single formula; `should_expose()` in `mqtt_bridge.py` implements it and everything else (publishing, cleanup, catalog `exposed` flags) derives from it.

> **Historical note (semantic change):** `exposed_entities` used to be the *complete* exposed list, with `included_domains` as UI sugar. It is now additions-only. This is what lets the Community Manager show "manually exposed" as a distinct, comprehensible concept — and keeps the noisy-domain default meaningful.

Cloud enrollment seeds `included_domains` = `SELECTABLE_DOMAINS − NOISY_DOMAINS` (`sensor`, `binary_sensor`, `automation`, `device_tracker`, `person`) and `exposed_entities` = `[]`: the platform's device list stays a device list; specific sensors are opt-in.

---

## Key Design Decisions

1. **The data plane is one class.** `TurziMqttBridge` owns the connection, both directions of traffic, and all protocol obligations. Cloud concerns (catalog, enrollment) live outside it — the bridge itself works identically against any broker, cloud or local, which is what keeps the self-hosted mode honest.

2. **Origin attribution via tracked contexts.** Every HA service call the bridge makes records its `Context` id; state-change events are classified by context — our own context → `turzi` (with the originating `command_id`), `parent_id` → `automation`, `user_id` → `core_user`, none → `physical`. This is the connector-side half of the platform's audit trail.

3. **Command safety is local and non-negotiable.** Expiry (`issued_at + ttl_seconds`), the TTL ceiling (`DEFAULT_TTL_CEILING_SECONDS = 300`, configurable only on the core — last line of defense against a compromised publisher), and `command_id` dedupe (retention ≥ ceiling) are all enforced here regardless of deployment mode. Acks are published exactly once per `command_id`, `failed` with a reason when anything is rejected.

4. **No artificial latency.** A legacy 100 ms sleep in the command path (a Node-RED-era artifact) was removed; command→ack now measures ~40 ms on a LAN. Don't add delays to "smooth" anything — clients do optimistic UI and reconcile on the state echo (see PROTOCOL.md client practice).

5. **Catalog goes over HTTPS, never MQTT.** The catalog enumerates *unexposed* entities; broker topics are readable by house clients. `build_catalog()` covers every entity in `SELECTABLE_DOMAINS` with `exposed`/`locally_blocked` flags plus `last_seen`/`added_on`, and each registration refreshes core/bridge/protocol versions (enrollment happens once; versions change forever).

6. **The privacy blocklist always wins.** `never_expose` is honored in every mode, including against a remote `config/exposure` revision — local exclusion beats platform instruction, and the catalog reports the discrepancy so the platform can display it (locked at the installation).

7. **Options never require restart.** Option updates diff the old/new effective sets: newly exposed entities publish immediately, newly excluded ones get an empty retained payload (Entity Cleanup). Same path handles remote exposure revisions.

8. **Clean session is a security requirement, not a tuning choice.** A persistent session would queue commands for an offline house and execute them on reconnect — exactly what expiry exists to prevent. See PROTOCOL.md §Deployment Modes.

---

## Cloud Lifecycle

```
TCM generates TRZ-XXXX-XXXX-XXXX ──► config flow (cloud) ──► POST /enroll
      ──► data: house_id + bridge_token + MQTT credential
      ──► bridge connects (LWT, retained states) · TurziCloudSync registers catalog
      ──► TCM shows "bridge online" + device catalog

Steady state: states/availability/acks up (MQTT) · commands down (MQTT, platform-published)
              catalog on registry changes (HTTPS, debounced)

Unlink (platform side): next API call → 401 token_revoked
      ──► repair issue in HA, bridge stops reconnecting, operator re-enrolls
```

Enrollment errors are surfaced in the config flow (`token_unknown`, `token_expired_or_used`, connectivity). The enrollment token is single-use; a failed attempt may retry the same token until it expires.

---

## Testing Against a Real Stack

The platform side (API, broker, Community Manager) lives in the `turzi-apps` repo; its dev stack runs the API + Postgres in Docker and Mosquitto 2.x with dynsec (TCP :1883, WebSockets :9001). Point a dev HA at it by enrolling normally with a token generated in the TCM — the whole loop (enrollment → catalog → placement → live control → audit ledger) is exercisable end-to-end. Useful checks:

- `mosquitto_sub -t 'house/{id}/#' -v` with the community's client credential shows exactly what apps see (subscribe-only: a denied subscribe is **silent** — a connected client receiving nothing usually means stale ACLs; rotate the credential).
- The HA Logbook records every executed command with actor metadata; the platform's `community_events` ledger records the resulting state changes with origin attribution.

---

## Known Issues / Next Steps

- [ ] Multiple config entries (multiple houses on one HA) are untested end-to-end in cloud mode.
- [ ] `alarm_control_panel` command mapping supports the full arm-mode table (see PROTOCOL.md); vacation/custom-bypass modes are untested against real panels.
- [ ] Heartbeat topics are still answered for v1.0 compatibility; removal is scheduled for the next major protocol version.
- [ ] Tag a release so HACS resolves the version badge.
