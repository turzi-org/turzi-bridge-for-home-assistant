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
    CONF_ADDITIONAL_ENTITIES,
    CONF_EXCLUDED_ENTITIES,
    CONF_EXPOSE_LABEL,
    CONF_INCLUDED_DOMAINS,
    CONF_LABEL_MODE,
    DEFAULT_EXPOSE_LABEL,
    DEFAULT_INCLUDED_DOMAINS,
    DEFAULT_LABEL_MODE,
    DOMAIN,
    SIGNAL_CONFIG_UPDATED,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_entry(hass: HomeAssistant, entry_id: str | None = None):
    """Return a config entry by ID, or the first one if no ID given."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return None
    if entry_id:
        return next((e for e in entries if e.entry_id == entry_id), None)
    return entries[0]


def _get_bridge(hass: HomeAssistant, entry_id: str | None = None):
    """Return the TurziMqttBridge for a config entry."""
    entry = _get_entry(hass, entry_id)
    if entry is None:
        return None
    return hass.data.get(DOMAIN, {}).get(entry.entry_id)


# ---------------------------------------------------------------------------
# WebSocket: read-only GET handlers
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
            "expose_label": entry.options.get(CONF_EXPOSE_LABEL, DEFAULT_EXPOSE_LABEL),
            "label_mode": entry.options.get(CONF_LABEL_MODE, DEFAULT_LABEL_MODE),
            "included_domains": entry.options.get(CONF_INCLUDED_DOMAINS, DEFAULT_INCLUDED_DOMAINS),
            "additional_entities": entry.options.get(CONF_ADDITIONAL_ENTITIES, []),
            "excluded_entities": entry.options.get(CONF_EXCLUDED_ENTITIES, []),
        },
    )


@callback
def websocket_get_entities(hass: HomeAssistant, connection, msg: dict) -> None:
    """Return all HA entities with exposure status."""
    entry = _get_entry(hass, msg.get("entry_id"))
    if entry is None:
        connection.send_error(msg["id"], "not_found", "No Turzi config entry found")
        return

    bridge = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    expose_label = entry.options.get(CONF_EXPOSE_LABEL, DEFAULT_EXPOSE_LABEL)
    additional = set(entry.options.get(CONF_ADDITIONAL_ENTITIES, []))
    excluded = set(entry.options.get(CONF_EXCLUDED_ENTITIES, []))
    auto_labeled: set[str] = bridge._auto_labeled_entities if bridge else set()

    registry = er.async_get(hass)
    result = []

    for reg_entry in registry.entities.values():
        if reg_entry.disabled_by:
            continue

        state = hass.states.get(reg_entry.entity_id)
        has_label = bool(expose_label and expose_label in reg_entry.labels)
        is_exposed = bridge.should_expose(reg_entry.entity_id) if bridge else has_label

        result.append(
            {
                "entity_id": reg_entry.entity_id,
                "name": (
                    reg_entry.name
                    or (state.attributes.get("friendly_name") if state else None)
                    or reg_entry.entity_id
                ),
                "domain": reg_entry.domain,
                "icon": reg_entry.icon or (state.attributes.get("icon") if state else None),
                "state": state.state if state else "unavailable",
                "is_exposed": is_exposed,
                "has_label": has_label,
                "is_auto_labeled": reg_entry.entity_id in auto_labeled,
                "is_additional": reg_entry.entity_id in additional,
                "is_excluded": reg_entry.entity_id in excluded,
            }
        )

    result.sort(key=lambda e: e["entity_id"])
    connection.send_result(msg["id"], result)


# ---------------------------------------------------------------------------
# WebSocket: live-update subscription
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
# REST views: mutations
# ---------------------------------------------------------------------------

class TurziConfigView(HomeAssistantView):
    """Save integration config options from the panel."""

    url = "/api/turzi/config"
    name = "api:turzi:config"

    @RequestDataValidator(
        vol.Schema(
            {
                vol.Required("entry_id"): cv.string,
                vol.Optional(CONF_EXPOSE_LABEL): cv.string,
                vol.Optional(CONF_LABEL_MODE): vol.In(["seed", "automatic", "mixed"]),
                vol.Optional(CONF_INCLUDED_DOMAINS): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional(CONF_ADDITIONAL_ENTITIES): vol.All(cv.ensure_list, [cv.entity_id]),
                vol.Optional(CONF_EXCLUDED_ENTITIES): vol.All(cv.ensure_list, [cv.entity_id]),
            }
        )
    )
    async def post(self, request, data: dict):
        """Handle config update from panel."""
        hass = request.app["hass"]
        entry = _get_entry(hass, data.pop("entry_id"))
        if entry is None:
            return self.json_message("Entry not found", status_code=404)

        # Normalise label to lowercase
        if CONF_EXPOSE_LABEL in data:
            data[CONF_EXPOSE_LABEL] = data[CONF_EXPOSE_LABEL].strip().lower()

        new_options = {**entry.options, **data}
        hass.config_entries.async_update_entry(entry, options=new_options)
        async_dispatcher_send(hass, SIGNAL_CONFIG_UPDATED)
        return self.json({"success": True})


class TurziEntityToggleView(HomeAssistantView):
    """Add or remove the expose label from a single entity."""

    url = "/api/turzi/entities/toggle"
    name = "api:turzi:entities:toggle"

    @RequestDataValidator(
        vol.Schema(
            {
                vol.Required("entry_id"): cv.string,
                vol.Required("entity_id"): cv.entity_id,
                vol.Required("expose"): cv.boolean,
            }
        )
    )
    async def post(self, request, data: dict):
        """Toggle entity exposure."""
        hass = request.app["hass"]
        entry = _get_entry(hass, data["entry_id"])
        if entry is None:
            return self.json_message("Entry not found", status_code=404)

        expose_label = entry.options.get(CONF_EXPOSE_LABEL, "")
        if not expose_label:
            return self.json_message("No expose label configured", status_code=400)

        registry = er.async_get(hass)
        reg_entry = registry.async_get(data["entity_id"])
        if reg_entry is None:
            return self.json_message("Entity not found", status_code=404)

        new_labels = (
            reg_entry.labels | {expose_label}
            if data["expose"]
            else reg_entry.labels - {expose_label}
        )
        registry.async_update_entity(data["entity_id"], labels=new_labels)
        async_dispatcher_send(hass, SIGNAL_CONFIG_UPDATED)
        return self.json({"success": True})


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

async def async_register_websockets(hass: HomeAssistant) -> None:
    """Register all WebSocket commands and REST views."""
    hass.http.register_view(TurziConfigView)
    hass.http.register_view(TurziEntityToggleView)

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
