"""The turzi Bridge integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.start import async_at_started

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
    """Set up turzi Bridge from a config entry."""

    # One-time migration: seed exposed_entities for entries that used the old
    # label-based options schema (which had no exposed_entities key).
    if CONF_EXPOSED_ENTITIES not in entry.options:
        await _async_migrate_options(hass, entry)

    bridge = TurziMqttBridge.from_config_entry(hass, entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = bridge

    async def _start_bridge(_hass: HomeAssistant) -> None:
        """Start the bridge once HA has finished starting."""
        await bridge.async_start()

    async_at_started(hass, _start_bridge)

    await async_register_panel(hass)
    await async_register_websockets(hass)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    _LOGGER.info(
        "turzi Bridge set up for house '%s' — will connect after HA start",
        entry.data.get("house_id", "unknown"),
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TurziConfigEntry) -> bool:
    """Unload a turzi Bridge config entry."""
    bridge: TurziMqttBridge | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    if bridge:
        await bridge.async_stop()

    if not hass.data.get(DOMAIN):
        async_unregister_panel(hass)

    if DOMAIN in hass.data and not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)

    _LOGGER.info(
        "turzi Bridge unloaded for house '%s'",
        entry.data.get("house_id", "unknown"),
    )
    return True


async def _async_migrate_options(hass: HomeAssistant, entry: TurziConfigEntry) -> None:
    """Seed exposed_entities from included_domains for entries without it.

    This handles upgrades from the old label-based config schema where
    exposed_entities did not exist. We seed the list by scanning the HA
    entity registry for entities whose domain is in included_domains.
    """
    included_domains: list[str] = entry.options.get(
        CONF_INCLUDED_DOMAINS, DEFAULT_INCLUDED_DOMAINS
    )
    domain_set = set(included_domains)

    registry = er.async_get(hass)
    exposed: list[str] = [
        reg_entry.entity_id
        for reg_entry in registry.entities.values()
        if not reg_entry.disabled_by and reg_entry.domain in domain_set
    ]

    new_options = {
        **entry.options,
        CONF_INCLUDED_DOMAINS: included_domains,
        CONF_EXPOSED_ENTITIES: exposed,
        CONF_AUTO_ADD_NEW: entry.options.get(CONF_AUTO_ADD_NEW, DEFAULT_AUTO_ADD_NEW),
    }

    # Strip legacy keys from old schema if present
    for legacy_key in ("expose_label", "label_mode", "additional_entities", "excluded_entities"):
        new_options.pop(legacy_key, None)

    hass.config_entries.async_update_entry(entry, options=new_options)
    _LOGGER.info(
        "Migrated config for house '%s': seeded %d exposed entities from domains %s",
        entry.data.get("house_id", "unknown"),
        len(exposed),
        sorted(domain_set),
    )


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
