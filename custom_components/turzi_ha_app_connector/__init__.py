"""The Turzi App Connector integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_AUTO_ADD_NEW,
    CONF_EXPOSED_ENTITIES,
    CONF_INCLUDED_DOMAINS,
    DEFAULT_AUTO_ADD_NEW,
    DEFAULT_INCLUDED_DOMAINS,
    DOMAIN,
    SIGNAL_CONFIG_UPDATED,
)
from .mqtt_bridge import TurziMqttBridge
from .panel import async_register_panel, async_unregister_panel
from .websockets import async_register_websockets

_LOGGER = logging.getLogger(__name__)

type TurziConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: TurziConfigEntry) -> bool:
    """Set up Turzi App Connector from a config entry."""
    bridge = TurziMqttBridge.from_config_entry(hass, entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = bridge

    await bridge.async_start()

    await async_register_panel(hass)
    await async_register_websockets(hass)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    _LOGGER.info(
        "Turzi App Connector set up for house '%s'",
        entry.data.get("house_id", "unknown"),
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TurziConfigEntry) -> bool:
    """Unload a Turzi App Connector config entry."""
    bridge: TurziMqttBridge | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    if bridge:
        await bridge.async_stop()

    if not hass.data.get(DOMAIN):
        async_unregister_panel(hass)

    if DOMAIN in hass.data and not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)

    _LOGGER.info(
        "Turzi App Connector unloaded for house '%s'",
        entry.data.get("house_id", "unknown"),
    )
    return True


async def _async_options_updated(hass: HomeAssistant, entry: TurziConfigEntry) -> None:
    """Handle options update — sync bridge config without full reload."""
    bridge: TurziMqttBridge | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if bridge is None:
        return

    bridge.update_config(
        exposed_entities=entry.options.get(CONF_EXPOSED_ENTITIES, []),
        included_domains=entry.options.get(CONF_INCLUDED_DOMAINS, DEFAULT_INCLUDED_DOMAINS),
        auto_add_new=entry.options.get(CONF_AUTO_ADD_NEW, DEFAULT_AUTO_ADD_NEW),
    )

    # Notify the panel to refresh
    async_dispatcher_send(hass, SIGNAL_CONFIG_UPDATED)

    _LOGGER.info(
        "Config updated for house '%s'",
        entry.data.get("house_id", "unknown"),
    )
