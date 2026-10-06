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
│   ├── subentries: domain_filter | entity_filter | exclusion (one row each)
│   └── options: auto_add_new, filter_snapshot[], config_revision
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
│   ├── POST /catalog on startup + registry and row changes (debounced) — the publish scope
│   ├── Refreshes bridge/core versions with every registration
│   └── 401 token_revoked → repair issue prompting re-enrollment, bridge stops
│
├── Enrollment                 enrollment.py    (cloud mode only)
│   └── POST /enroll: exchanges the TRZ- token for house_id + bridge_token + MQTT credential
│
├── Config flow                config_flow.py
│   ├── Menu: cloud (token) | manual (broker form), then «Opciones» — plus reconfigure
│   └── Options flow (Configure): «Opciones», automatic exposure (see Data Model)
│
└── Subentry flows             subentry_flows.py
    └── Add domain filter (domain, then its classes) | entity filter | exclusion; edit a row
```

There is **no custom panel, no WebSocket/REST API, no bundled frontend** — earlier versions had a sidebar panel; it was deleted when exposure management moved to the native options flow and (for the platform-facing parts) to the Turzi Community Manager. If you find references to `panel.py`, `websockets.py` or `frontend/`, they are historical.

---

## File Structure

```
custom_components/turzi_bridge/
├── __init__.py           Setup/teardown; wires bridge + cloud sync per entry
├── config_flow.py        Menu flow (cloud/manual), reconfigure, options flow
├── const.py              CONF keys, subentry types, SELECTABLE_DOMAINS,
│                         DEFAULT_FILTERS, DOOR_AND_SAFETY_CLASSES,
│                         DOMAIN_ATTRIBUTES (+ HA→protocol key renames),
│                         DEFAULT_TTL_CEILING_SECONDS (300, local-only by design)
├── exposure.py           PublishScope: the one publishing rule (no HA imports)
├── scope.py              reads the rule from the entry's subentries; entities, words
├── subentry_flows.py     the bridge page's three add buttons (and editing a row)
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

### `config_entry.subentries` (what is published — one row each, no restart)

Each filter and each exclusion is a **subentry** (entry version 3), so Home Assistant lists it on the bridge's page with an edit button and a delete action, and gives each type its own add button (`subentry_flows.py`):

| Type | `data` | Meaning |
|---|---|---|
| `domain_filter` | `{"domain": str, "device_classes": [str]}` | Every entity of the domain, or only those classes. One per domain (its `unique_id` is the domain) |
| `entity_filter` | `{"entities": [str]}` | Those entities, of any domain |
| `exclusion` | `{"entities": [str]}` | Never published; wins over every filter, in every mode, survives re-enrollment |

**An entity is published when any filter matches it and no exclusion names it.** That is the single formula. `exposure.PublishScope` compiles the filters (no Home Assistant imports, so it can be read and tested alone), `scope.py` reads them from the entry and walks the entities, and everything else (publishing, cleanup, command gating, the catalog and its `exposed` flags, the flows' counts) derives from those two. A device class is the effective one Home Assistant writes into the state, so an installer's **Show as** wins over the integration's class; without a state, the registry gives the same answer. A sensor whose class changes out of a filter has its retained state cleared on that state change. Adding, editing or deleting a row fires the entry's update listener, which applies it at once.

### `config_entry.options` (mutable at runtime, no restart)

| Key | Type | Meaning |
|---|---|---|
| `auto_add_new` | bool | On (default): a new entity that matches a domain filter is published by itself. Off: domain filters cover only `filter_snapshot` |
| `filter_snapshot` | list[str] | The entities the domain filters matched when one was last saved (setup, a domain filter's flow, Configure). An entry migrated with `auto_add_new` off takes it at its first start |
| `config_revision` | int | Last applied remote exposure revision (PROTOCOL.md §5) |

Setup (cloud or manual) ends in an **Opciones** step and creates the entry with the preloaded domain filters (`DEFAULT_FILTERS`): `alarm_control_panel`, `climate`, `cover`, `fan`, `light`, `lock`, `siren`, `switch`, and `binary_sensor` limited to the door and life-safety classes (`DOOR_AND_SAFETY_CLASSES`). The platform cannot ask for an entity its catalog never listed, so without that filter no building reported a door contact (turzi-apps `DEFERRED_WORK.md` D54).

The v2 → v3 migration in `async_migrate_entry` turns the old keys into rows without changing what is published (`included_domains` → domain filters, `exposed_entities` → an entity filter, `never_expose` → an exclusion), and adds the door and safety filter, logged, to an entry that did not publish binary sensors. An entry from a newer bridge is refused. A remote exposure revision replaces the filter rows and leaves the exclusions.

---

## Key Design Decisions

1. **The data plane is one class.** `TurziMqttBridge` owns the connection, both directions of traffic, and all protocol obligations. Cloud concerns (catalog, enrollment) live outside it — the bridge itself works identically against any broker, cloud or local, which is what keeps the self-hosted mode honest.

2. **Origin attribution via tracked contexts.** Every HA service call the bridge makes records its `Context` id; state-change events are classified by context — our own context → `turzi` (with the originating `command_id`), `parent_id` → `automation`, `user_id` → `core_user`, none → `physical`. This is the connector-side half of the platform's audit trail.

3. **Command safety is local and non-negotiable.** Expiry (`issued_at + ttl_seconds`), the TTL ceiling (`DEFAULT_TTL_CEILING_SECONDS = 300`, configurable only on the core — last line of defense against a compromised publisher), and `command_id` dedupe (retention ≥ ceiling) are all enforced here regardless of deployment mode. Acks are published exactly once per `command_id`, `failed` with a reason when anything is rejected.

4. **No artificial latency.** A legacy 100 ms sleep in the command path (a Node-RED-era artifact) was removed; command→ack now measures ~40 ms on a LAN. Don't add delays to "smooth" anything — clients do optimistic UI and reconcile on the state echo (see PROTOCOL.md client practice).

5. **Catalog goes over HTTPS, never MQTT.** The catalog is the publish scope, the entities the privacy blocklist holds back included, flagged `locally_blocked`; broker topics are readable by house clients, and those blocked entities must not be. (Until 2026-08-09 it listed every entity in `SELECTABLE_DOMAINS`; it was narrowed so the platform never sees unwanted entities.) `build_catalog()` reports each with `exposed`/`locally_blocked` flags plus `last_seen`/`added_on`, and each registration refreshes core/bridge/protocol versions (enrollment happens once; versions change forever). Since 2026-10 each entity also carries its **`device`** — HA's device-registry id, the name a person gave it (else the integration's), manufacturer, model, firmware — so the platform can group entities into devices on its Dispositivos tab (turzi-apps `INTEGRATIONS.md` §3.9, `BRIDGE_CLOUD_API.md` §3). The platform never lets a device fill a fixture role; this is grouping only. Because a device rename changes the *device* registry, the catalog is re-registered on `EVENT_DEVICE_REGISTRY_UPDATED` as well as on entity-registry changes.

6. **Exclusions always win.** They are honored in every mode, including against a remote `config/exposure` revision, which replaces the filter rows and never the exclusions — local exclusion beats platform instruction, and the catalog reports the discrepancy so the platform can display it (locked at the installation).

7. **Rows and options never require restart.** A row added, edited or deleted, or an option saved, fires the update listener, which diffs the old/new effective sets: newly exposed entities publish immediately, newly excluded ones get an empty retained payload (Entity Cleanup). Same path handles remote exposure revisions.

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

## Tests

`tests/` runs the integration against a real Home Assistant core through `pytest-homeassistant-custom-component`, which pins the Home Assistant version it installs (2026.9 needs Python 3.14):

```bash
pip install -r requirements_test.txt
pytest
```

They cover the publishing rule, the catalog, publishing and retained cleanup, setup, the three add flows and editing a row, Configure, remote revisions and the config-entry migrations. There is no CI here: run them before pushing.

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
