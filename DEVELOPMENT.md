# Turzi HA App Connector — Development Guide

> **Purpose:** This document is a handoff guide for developers (and AI agents) picking up this project. It describes the complete current architecture, every design decision made, the file structure, the data flow, and the exact state of the codebase as of the last session.

---

## Project Summary

`turzi_ha_app_connector` is a custom Home Assistant integration that bridges HA entity states to the Turzi mobile app via an external MQTT broker. It was originally built with a label-based entity management system; that was completely replaced with a simpler `exposed_entities` set stored in `config_entry.options`, managed entirely through a custom HA sidebar panel.

**Repo:** `https://github.com/turzi-org/turzi-home-assistant-integrations`  
**Integration path:** `custom_components/turzi_ha_app_connector/`  
**HA domain:** `turzi_ha_app_connector`

---

## Architecture Overview

```
Home Assistant
│
├── config_entry (one per house)
│   ├── data: broker credentials + house_id (set at setup, changed via Reconfigure)
│   └── options: exposed_entities[], included_domains[], auto_add_new
│
├── TurziMqttBridge           mqtt_bridge.py
│   ├── Maintains aiomqtt connection with exponential backoff reconnect
│   ├── Publishes state changes for exposed entities to MQTT
│   ├── Receives commands from app → calls HA services
│   ├── Tracks connection status + event log (last 50 entries)
│   └── Dispatches SIGNAL_CONFIG_UPDATED on connect/disconnect
│
├── WebSocket API             websockets.py
│   ├── turzi/config          → get current options
│   ├── turzi/entities        → all HA entities with exposure status
│   ├── turzi/status          → bridge connection status + event log
│   └── turzi/subscribe       → push events when config/status changes
│
├── REST API                  websockets.py
│   ├── POST /api/turzi/config           → save included_domains + auto_add_new
│   └── POST /api/turzi/entities/update  → expose/exclude one or many entities
│
└── Sidebar Panel             frontend/turzi-panel.js + turzi-styles.js
    ├── Served from: /api/turzi_ha_app_connector/panel/<file>
    ├── Tab: Entities (merged with settings)
    └── Tab: Status
```

---

## File Structure

```
custom_components/turzi_ha_app_connector/
├── __init__.py           Setup/teardown + one-time migration from old label schema
├── config_flow.py        UI flow for broker setup (ConfigFlow + reconfigure step)
├── const.py              All constants — config keys, defaults, MQTT params
├── manifest.json         Integration metadata for HA + HACS
├── mqtt_bridge.py        Core MQTT bridge (TurziMqttBridge class)
├── panel.py              Registers the sidebar panel + static file serving
├── websockets.py         WebSocket commands + REST views
├── strings.json          UI strings (EN)
├── translations/en.json  Translated strings
├── brand/
│   ├── logo.png          Used by HA integrations page
│   └── icon.png
└── frontend/
    ├── turzi-panel.js    Main panel web component (ES module)
    ├── turzi-styles.js   CSS styles module (imported by panel.js)
    ├── turzi-logo.png    Logo served to the panel header
    └── preview.html      Standalone browser preview (mocks HA environment)
```

---

## Data Model

### `config_entry.data` (set at initial setup, changed only via Reconfigure)

| Key | Type | Description |
|---|---|---|
| `broker` | str | MQTT broker hostname |
| `port` | int | MQTT port (default 1883) |
| `username` | str \| None | MQTT auth username |
| `password` | str \| None | MQTT auth password |
| `house_id` | str | Topic prefix identifier |
| `use_tls` | bool | Whether to use TLS |

### `config_entry.options` (mutable at runtime via the panel)

| Key | Type | Description |
|---|---|---|
| `exposed_entities` | list[str] | All entity IDs currently exposed to MQTT |
| `included_domains` | list[str] | Domains used for auto-exposure |
| `auto_add_new` | bool | Whether to auto-expose new entities from included domains |

> **Important:** `exposed_entities` is the single source of truth for what gets published to MQTT. The bridge reads this as a `set[str]` internally. `included_domains` controls the UI (domain picker) and auto-add behaviour only — it does NOT filter at publish time.

---

## Key Design Decisions

### 1. No Labels
The original implementation used HA entity labels (`expose_label`, `label_mode: seed/automatic/mixed`). This was replaced entirely with a flat `exposed_entities` list. Labels are no longer created, read, or managed anywhere.

### 2. One-Time Migration
On first startup after upgrading from the label schema, `__init__.py` checks if `CONF_EXPOSED_ENTITIES` is missing from `entry.options`. If so, it calls `_async_migrate_options()` which:
- Reads the entity registry
- Seeds `exposed_entities` with all non-disabled entities whose domain is in `included_domains`
- Strips old keys (`expose_label`, `label_mode`, etc.)

### 3. Options Never Require Restart
All config mutations go through `hass.config_entries.async_update_entry()`. The `_async_options_updated` listener in `__init__.py` calls `bridge.update_config()` which diffs the old/new exposed sets and publishes/clears MQTT messages in real time.

### 4. Panel Static Files
`panel.py` registers the **entire `frontend/` directory** as a static path at `/api/turzi_ha_app_connector/panel/`. This means:
- JS: `/api/turzi_ha_app_connector/panel/turzi-panel.js`
- Logo: `/api/turzi_ha_app_connector/panel/turzi-logo.png`
- Styles module: `/api/turzi_ha_app_connector/panel/turzi-styles.js`

The panel JS uses ES module `import` syntax: `import { STYLES } from "./turzi-styles.js"`.

### 5. Entity Endpoint Includes Non-Registry Entities
`websocket_get_entities` unions the HA entity registry with `hass.states.async_all()` to catch groups, helpers, and any states not in the registry. Registry-disabled entities are excluded.

### 6. Status Tracking
`TurziMqttBridge` maintains:
- `_connection_status`: `"connecting"` | `"connected"` | `"reconnecting"` | `"disconnected"`
- `_reconnect_count`, `_last_connect_time`, `_last_disconnect_time`
- `_event_log`: `collections.deque(maxlen=50)` of `{time, level, message}` dicts

`SIGNAL_CONFIG_UPDATED` is dispatched on connect/disconnect so the panel's Status tab refreshes live.

---

## Panel UI

### Tab: Entities (merged with Settings)

**Top: Exposure Settings card** (auto-saves with 1s debounce)
- Toggle: Auto-expose new entities
- Domain picker: searchable input → dropdown with entity counts → removable orange tags
- "Select all / Clear all" button

**Below: Entity list**
- Search bar (name or entity ID)
- Domain filter chips (from actual entity domains + included_domains, with counts)
- Stats line: `N of M exposed · K shown`
- Batch action bar (appears on selection): Expose / Exclude / Clear
- Select-all row checkbox
- Entity rows:
  - Left: batch-select checkbox
  - Icon (accent color = orange when exposed)
  - Name + entity_id
  - Status badge: `Auto Exposed` / `Manually Exposed` / `User Excluded` / *(none)*
  - Right: `ha-switch` for individual toggle

### Tab: Status

- Connection indicator (pulsing when reconnecting)
- Broker host, port, TLS, house_id
- Exposed count, published count, reconnect count
- Last connected / last disconnected timestamps
- Activity log (last 50, reverse-chronological, color-coded by level)

---

## MQTT Bridge Internals

### Connection Loop (`_connection_loop`)
- Runs as an `asyncio.Task`
- Uses `aiomqtt.Client` as an async context manager
- On connect: subscribes to topics, publishes all current states, then listens for messages
- On `MqttError`: logs event, increments `_reconnect_count`, waits with exponential backoff (5s → 60s max)
- Dispatches `SIGNAL_CONFIG_UPDATED` on both connect and disconnect

### Exposure Check
```python
def should_expose(self, entity_id: str) -> bool:
    return entity_id in self._exposed_entities  # set[str]
```

### Config Update (`update_config`)
Called from `_async_options_updated` without restarting the bridge:
1. Diffs old published entities vs new exposed set
2. Publishes newly exposed entities
3. Clears (empty retain) newly excluded entities

### Auto-Add (Registry Listener)
On `entity_registry_updated` event with `action="create"`:
- If `auto_add_new` is True and the domain is in `included_domains`
- Adds entity to `_exposed_entities`, publishes state, persists to options

---

## WebSocket API Reference

All commands use `hass.connection.sendMessagePromise({type: "turzi/..."})` from the frontend.

| Command | Returns |
|---|---|
| `turzi/config` | `{entry_id, house_id, included_domains, exposed_entities, auto_add_new}` |
| `turzi/entities` | `[{entity_id, name, domain, icon, state, is_exposed, in_domain}]` |
| `turzi/status` | `{status, broker, port, use_tls, house_id, reconnect_count, last_connect_time, last_disconnect_time, published_count, exposed_count, event_log}` |
| `turzi/subscribe` | Subscription — pushes `{type:"event"}` on any config/status change |

## REST API Reference

| Endpoint | Body | Effect |
|---|---|---|
| `POST /api/turzi/config` | `{entry_id, included_domains?, auto_add_new?}` | Saves settings. Adding domains auto-exposes all their current entities. |
| `POST /api/turzi/entities/update` | `{entry_id, entity_ids: string[], expose: bool}` | Exposes or excludes one or many entities atomically. |

---

## Development & Local Preview

### Browser Preview (no HA needed)

Open `frontend/preview.html` directly in a browser. It mocks:
- `ha-icon` (inline SVG)
- `ha-switch` (CSS toggle)
- The `hass` object with `connection.sendMessagePromise` and `callApi`

The mock data includes entities across several domains in all 4 exposure states. Edit `MOCK_ENTITIES` and `MOCK_CONFIG` at the top of the file to test different scenarios.

After editing `turzi-panel.js` or `turzi-styles.js`, just hard-refresh the browser (`Cmd+Shift+R`).

### Installing in HA

Copy the `custom_components/turzi_ha_app_connector/` folder to your HA `config/custom_components/` and restart. The panel JS is served without cache headers and uses a `?v={mtime}` cache-bust query string so browsers pick up changes on HA restart.

---

## Known Issues / Next Steps

### Outstanding
- [ ] `preview.html` does not load `turzi-logo.png` (path mismatch in file:// context) — logo is hidden gracefully via `onerror`
- [ ] `turzi/subscribe` event does not differentiate between config change and status change — the panel always re-fetches all three endpoints on any event
- [ ] No pagination for very large entity lists (1000+ entities may feel slow)
- [ ] The dropdown in the domain picker closes on `document.addEventListener("click", ..., {once:true})` — this is fragile if the event is captured by another element first

### Potential Improvements
- [ ] Add entity count summary per domain in the entity list header
- [ ] Allow sorting entity list by name / exposure status
- [ ] Show a "last published" timestamp per entity in the status tab
- [ ] Support multiple config entries (multiple houses) in the panel — currently always uses the first entry
- [ ] Tag release (e.g. `v1.0.0`) so HACS can resolve the version badge

---

## Commit History (Recent)

```
d588a2e feat: merge Settings into Entities tab, searchable domain picker
3e641e8 feat: status tab, domain chip counts, entity union fix, branding
a0edcb1 feat: branding + exposed_entities migration
a692ad2 fix(panel): clearer status badge labels
329f04e fix(panel): revert expose control back to ha-switch
9bc1e7f fix(panel): redesign entity row UX
52f9e22 fix: use mdi:alpha-t-circle for sidebar panel icon
5c39176 refactor: replace label system with simple exposed_entities set
```
