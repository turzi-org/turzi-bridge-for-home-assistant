"""The Turzi App Connector integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

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
)
from .mqtt_bridge import TurziMqttBridge
from .panel import async_register_panel, async_unregister_panel
from .websockets import async_register_websockets

_LOGGER = logging.getLogger(__name__)

type TurziConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: TurziConfigEntry) -> bool:
    """Set up Turzi App Connector from a config entry."""
    bridge = TurziMqttBridge.from_config_entry(hass, entry)

    # Store the bridge instance
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = bridge

    # Start the MQTT bridge
    await bridge.async_start()

    # Register sidebar panel and WebSocket/REST API
    await async_register_panel(hass)
    await async_register_websockets(hass)

    # Register listener for options updates (entity filter changes)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    _LOGGER.info(
        "Turzi App Connector set up for house '%s'",
        entry.data.get("house_id", "unknown"),
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TurziConfigEntry) -> bool:
    """Unload a Turzi App Connector config entry."""
    bridge: TurziMqttBridge | None = hass.data.get(DOMAIN, {}).pop(
        entry.entry_id, None
    )

    if bridge:
        await bridge.async_stop()

    # Unregister panel if no more entries remain
    if not hass.data.get(DOMAIN):
        async_unregister_panel(hass)

    # Clean up domain data if no more entries
    if DOMAIN in hass.data and not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)

    _LOGGER.info(
        "Turzi App Connector unloaded for house '%s'",
        entry.data.get("house_id", "unknown"),
    )
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: TurziConfigEntry
) -> None:
    """Handle options update — update the entity filter without full reload."""
    bridge: TurziMqttBridge | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if bridge is None:
        return

    bridge.update_entity_filter(
        expose_label=entry.options.get(CONF_EXPOSE_LABEL, DEFAULT_EXPOSE_LABEL),
        label_mode=entry.options.get(CONF_LABEL_MODE, DEFAULT_LABEL_MODE),
        included_domains=entry.options.get(
            CONF_INCLUDED_DOMAINS, DEFAULT_INCLUDED_DOMAINS
        ),
        additional_entities=entry.options.get(CONF_ADDITIONAL_ENTITIES, []),
        excluded_entities=entry.options.get(CONF_EXCLUDED_ENTITIES, []),
    )

    _LOGGER.info(
        "Entity filter updated for house '%s'",
        entry.data.get("house_id", "unknown"),
    )
