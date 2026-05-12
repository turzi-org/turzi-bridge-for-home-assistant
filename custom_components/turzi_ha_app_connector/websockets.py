"""WebSocket and REST API handlers for the Turzi panel."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.data_validator import RequestDataValidator
from homeassistant.components.websocket_api import async_register_command, decorators
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send

from .const import (
    CONF_AUTO_ADD_NEW,
    CONF_EXPOSED_ENTITIES,
    CONF_INCLUDED_DOMAINS,
    DEFAULT_AUTO_ADD_NEW,
    DEFAULT_INCLUDED_DOMAINS,
    DOMAIN,
    SIGNAL_CONFIG_UPDATED,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_entry(hass: HomeAssistant, entry_id: str | None = None):
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return None
    if entry_id:
        return next((e for e in entries if e.entry_id == entry_id), None)
    return entries[0]


def _get_bridge(hass: HomeAssistant, entry_id: str | None = None):
    entry = _get_entry(hass, entry_id)
    if entry is None:
        return None
    return hass.data.get(DOMAIN, {}).get(entry.entry_id)


# ---------------------------------------------------------------------------
# WebSocket: turzi/config
# ---------------------------------------------------------------------------

@callback
def websocket_get_config(hass: HomeAssistant, connection, msg: dict) -> None:
    """Return current integration config options."""
    entry = _get_entry(hass, msg.get("entry_id"))
    if entry is None:
        connection.send_error(msg["id"], "not_found", "No Turzi config entry found")
        return
    connection.send_result(
        msg["id"],
        {
            "entry_id": entry.entry_id,
            "house_id": entry.data.get("house_id", ""),
            "included_domains": entry.options.get(CONF_INCLUDED_DOMAINS, DEFAULT_INCLUDED_DOMAINS),
            "exposed_entities": entry.options.get(CONF_EXPOSED_ENTITIES, []),
            "auto_add_new": entry.options.get(CONF_AUTO_ADD_NEW, DEFAULT_AUTO_ADD_NEW),
        },
    )


# ---------------------------------------------------------------------------
# WebSocket: turzi/entities
# ---------------------------------------------------------------------------

@callback
def websocket_get_entities(hass: HomeAssistant, connection, msg: dict) -> None:
    """Return all HA entities with exposure status."""
    entry = _get_entry(hass, msg.get("entry_id"))
    if entry is None:
        connection.send_error(msg["id"], "not_found", "No Turzi config entry found")
        return

    bridge = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    exposed_set: set[str] = set(entry.options.get(CONF_EXPOSED_ENTITIES, []))
    included_domains: set[str] = set(entry.options.get(CONF_INCLUDED_DOMAINS, DEFAULT_INCLUDED_DOMAINS))

    registry = er.async_get(hass)

    # Build registry map (non-disabled only)
    registry_map = {
        reg_entry.entity_id: reg_entry
        for reg_entry in registry.entities.values()
        if not reg_entry.disabled_by
    }

    # Union: registered entities + all live states (catches groups, helpers, etc.)
    all_ids = set(registry_map.keys()) | {s.entity_id for s in hass.states.async_all()}

    result = []
    for entity_id in all_ids:
        reg_entry = registry_map.get(entity_id)
        state = hass.states.get(entity_id)
        domain = entity_id.split(".")[0]
        is_exposed = bridge.should_expose(entity_id) if bridge else (entity_id in exposed_set)
        in_domain = domain in included_domains

        result.append(
            {
                "entity_id": entity_id,
                "name": (
                    (reg_entry.name if reg_entry else None)
                    or (state.attributes.get("friendly_name") if state else None)
                    or entity_id
                ),
                "domain": domain,
                "icon": (
                    (reg_entry.icon if reg_entry else None)
                    or (state.attributes.get("icon") if state else None)
                ),
                "state": state.state if state else "unavailable",
                "is_exposed": is_exposed,
                "in_domain": in_domain,
            }
        )

    result.sort(key=lambda e: e["entity_id"])
    connection.send_result(msg["id"], result)


# ---------------------------------------------------------------------------
# WebSocket: turzi/subscribe — live update push
# ---------------------------------------------------------------------------

@callback
@decorators.websocket_command({vol.Required("type"): "turzi/subscribe"})
@decorators.async_response
async def handle_subscribe_updates(hass: HomeAssistant, connection, msg: dict) -> None:
    """Push an event to the panel whenever config changes."""

    @callback
    def _on_update() -> None:
        connection.send_message({"id": msg["id"], "type": "event", "event": {}})

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(
        hass, SIGNAL_CONFIG_UPDATED, _on_update
    )
    connection.send_result(msg["id"])


# ---------------------------------------------------------------------------
# REST: POST /api/turzi/config — save settings
# ---------------------------------------------------------------------------

class TurziConfigView(HomeAssistantView):
    """Save integration settings from the panel."""

    url = "/api/turzi/config"
    name = "api:turzi:config"

    @RequestDataValidator(
        vol.Schema(
            {
                vol.Required("entry_id"): cv.string,
                vol.Optional(CONF_INCLUDED_DOMAINS): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional(CONF_AUTO_ADD_NEW): cv.boolean,
            }
        )
    )
    async def post(self, request, data: dict):
        """Save domain and auto_add_new settings.

        When included_domains changes, newly-included domain entities are
        added to exposed_entities. Removing a domain does NOT remove entities
        (user controls exposure via toggles).
        """
        hass = request.app["hass"]
        entry_id = data.pop("entry_id")
        entry = _get_entry(hass, entry_id)
        if entry is None:
            return self.json_message("Entry not found", status_code=404)

        new_options = {**entry.options}
        old_domains: set[str] = set(entry.options.get(CONF_INCLUDED_DOMAINS, DEFAULT_INCLUDED_DOMAINS))
        exposed: set[str] = set(entry.options.get(CONF_EXPOSED_ENTITIES, []))

        if CONF_INCLUDED_DOMAINS in data:
            new_domains: set[str] = set(data[CONF_INCLUDED_DOMAINS])
            added_domains = new_domains - old_domains

            # Auto-add all entities from newly-included domains
            if added_domains:
                registry = er.async_get(hass)
                for reg_entry in registry.entities.values():
                    if reg_entry.disabled_by:
                        continue
                    if reg_entry.domain in added_domains:
                        exposed.add(reg_entry.entity_id)

            new_options[CONF_INCLUDED_DOMAINS] = data[CONF_INCLUDED_DOMAINS]
            new_options[CONF_EXPOSED_ENTITIES] = list(exposed)

        if CONF_AUTO_ADD_NEW in data:
            new_options[CONF_AUTO_ADD_NEW] = data[CONF_AUTO_ADD_NEW]

        hass.config_entries.async_update_entry(entry, options=new_options)
        async_dispatcher_send(hass, SIGNAL_CONFIG_UPDATED)
        return self.json({"success": True})


# ---------------------------------------------------------------------------
# REST: POST /api/turzi/entities/update — toggle one or many entities
# ---------------------------------------------------------------------------

class TurziEntityUpdateView(HomeAssistantView):
    """Add or remove entities from the exposed set."""

    url = "/api/turzi/entities/update"
    name = "api:turzi:entities:update"

    @RequestDataValidator(
        vol.Schema(
            {
                vol.Required("entry_id"): cv.string,
                vol.Required("entity_ids"): vol.All(cv.ensure_list, [cv.entity_id]),
                vol.Required("expose"): cv.boolean,
            }
        )
    )
    async def post(self, request, data: dict):
        """Expose or un-expose a list of entities."""
        hass = request.app["hass"]
        entry = _get_entry(hass, data["entry_id"])
        if entry is None:
            return self.json_message("Entry not found", status_code=404)

        exposed: set[str] = set(entry.options.get(CONF_EXPOSED_ENTITIES, []))

        if data["expose"]:
            exposed.update(data["entity_ids"])
        else:
            exposed.difference_update(data["entity_ids"])

        new_options = {**entry.options, CONF_EXPOSED_ENTITIES: list(exposed)}
        hass.config_entries.async_update_entry(entry, options=new_options)
        async_dispatcher_send(hass, SIGNAL_CONFIG_UPDATED)
        return self.json({"success": True, "exposed_count": len(exposed)})


# ---------------------------------------------------------------------------
# WebSocket: turzi/status — broker connection status + event log
# ---------------------------------------------------------------------------

@callback
def websocket_get_status(hass: HomeAssistant, connection, msg: dict) -> None:
    """Return broker connection status and event log."""
    entry = _get_entry(hass, msg.get("entry_id"))
    if entry is None:
        connection.send_error(msg["id"], "not_found", "No Turzi config entry found")
        return
    bridge = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if bridge is None:
        connection.send_error(msg["id"], "not_found", "Bridge not running")
        return
    connection.send_result(msg["id"], bridge.get_status())


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

async def async_register_websockets(hass: HomeAssistant) -> None:
    """Register all WebSocket commands and REST views."""
    hass.http.register_view(TurziConfigView)
    hass.http.register_view(TurziEntityUpdateView)

    async_register_command(hass, handle_subscribe_updates)

    async_register_command(
        hass,
        "turzi/config",
        websocket_get_config,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): "turzi/config",
                vol.Optional("entry_id"): cv.string,
            }
        ),
    )
    async_register_command(
        hass,
        "turzi/entities",
        websocket_get_entities,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): "turzi/entities",
                vol.Optional("entry_id"): cv.string,
            }
        ),
    )
    async_register_command(
        hass,
        "turzi/status",
        websocket_get_status,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): "turzi/status",
                vol.Optional("entry_id"): cv.string,
            }
        ),
    )
