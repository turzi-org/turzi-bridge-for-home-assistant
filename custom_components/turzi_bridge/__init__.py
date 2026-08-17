"""The turzi Bridge integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers.start import async_at_started

from .cloud import TurziCloudSync
from .const import (
    CONF_AUTO_ADD_NEW,
    CONF_BRIDGE_TOKEN,
    CONF_CONFIG_REVISION,
    CONF_EXPOSED_ENTITIES,
    CONF_INCLUDED_DOMAINS,
    CONF_MODE,
    CONF_NEVER_EXPOSE,
    DEFAULT_AUTO_ADD_NEW,
    DEFAULT_INCLUDED_DOMAINS,
    DOMAIN,
    SIGNAL_CONFIG_UPDATED,
)
from .mqtt_bridge import TurziMqttBridge

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
    hass.data[DOMAIN][entry.entry_id] = {"bridge": bridge, "cloud": None}

    # Cloud-enrolled entries get the management plane: catalog registration
    # up (HTTPS) and remote exposure config down (catalog response + the
    # retained config/exposure topic).
    if entry.data.get(CONF_MODE) == "cloud" and entry.data.get(CONF_BRIDGE_TOKEN):
        cloud = TurziCloudSync(hass, entry)
        hass.data[DOMAIN][entry.entry_id]["cloud"] = cloud
        bridge.exposure_callback = cloud.async_apply_exposure
        bridge.config_revision = entry.options.get(CONF_CONFIG_REVISION)

        async def _on_unlinked() -> None:
            """Platform unlinked this bridge: stop and ask for a new key."""
            async_create_issue(
                hass,
                DOMAIN,
                f"unlinked_{entry.entry_id}",
                is_fixable=False,
                severity=IssueSeverity.ERROR,
                translation_key="unlinked",
            )
            entry.async_start_reauth(hass)
            hass.async_create_task(bridge.async_stop())

        bridge.unlink_callback = _on_unlinked

    async def _start_bridge(_hass: HomeAssistant) -> None:
        """Start the bridge once HA has finished starting."""
        await bridge.async_start()
        cloud_sync = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("cloud")
        if cloud_sync:
            cloud_sync.start()

    async_at_started(hass, _start_bridge)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    _LOGGER.info(
        "turzi Bridge set up for house '%s' — will connect after HA start",
        entry.data.get("house_id", "unknown"),
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TurziConfigEntry) -> bool:
    """Unload a turzi Bridge config entry."""
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None) or {}

    cloud: TurziCloudSync | None = data.get("cloud")
    if cloud:
        cloud.stop()

    bridge: TurziMqttBridge | None = data.get("bridge")
    if bridge:
        await bridge.async_stop()

    if DOMAIN in hass.data and not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)

    _LOGGER.info(
        "turzi Bridge unloaded for house '%s'",
        entry.data.get("house_id", "unknown"),
    )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: TurziConfigEntry) -> bool:
    """Migrate a config entry to the current schema version.

    **v1 → v2 — `included_domains` changed meaning, and the change opens up.**

    Under v1, `should_expose` was `entity_id in self._exposed_entities`, full
    stop; `included_domains` was only the filter deciding which NEWLY created
    entities auto-add was allowed to append to that list. A resident who
    unchecked `light.dormitorio` was done — the domain list had no say.

    Now a listed domain is exposed wholesale, so carrying the old value over
    verbatim would re-expose every entity in ~10 domains, including the exact
    ones somebody deliberately unchecked, without asking and without a trace.
    That is a privacy regression, and it is silent, which is the worst kind:
    the resident's phone gains devices and nothing announces it.

    So the migration keeps the effective exposure identical instead of the
    stored value identical: `exposed_entities` was the complete truth about
    what was published, and an empty `included_domains` makes v2's rule
    collapse back to exactly that set. Wholesale exposure stays available and
    off, one deliberate edit away in Exposure & privacy.

    Two kinds of v1 entry must NOT be touched, and both would be wrecked by
    clearing the list:

    - **Entries already created by this branch.** VERSION was bumped after the
      new exposure model shipped, so entries enrolled against it are stamped
      v1 while their `included_domains` already means wholesale — and their
      `exposed_entities` is `[]`, since it now holds manual additions only.
      Clearing would leave them exposing nothing at all. They are told apart
      by `mode` in `entry.data`: this branch stamps it on every entry it
      creates (cloud and manual alike) and v1 had no such key.
    - **The pre-`exposed_entities` label schema**, which has no per-entity
      curation to protect: there `included_domains` IS the whole intent, so it
      is left for `_async_migrate_options` to seed from.
    """
    if entry.version == 1:
        options = dict(entry.options)
        pre_branch = CONF_MODE not in entry.data
        curated = CONF_EXPOSED_ENTITIES in options
        previous = options.get(CONF_INCLUDED_DOMAINS, DEFAULT_INCLUDED_DOMAINS)

        if pre_branch and curated:
            options[CONF_INCLUDED_DOMAINS] = []
            _LOGGER.warning(
                "turzi Bridge: '%s' upgraded to the new exposure model. Listed "
                "domains are now exposed wholesale, so the previous list (%s) "
                "was cleared to keep exposure exactly as it is today — the %d "
                "entities already chosen, nothing new. Re-add domains under "
                "Settings → Devices → turzi Bridge → Configure to expose them "
                "wholesale.",
                entry.data.get("house_id", "unknown"),
                ", ".join(sorted(previous)) or "none",
                len(options.get(CONF_EXPOSED_ENTITIES) or []),
            )

        hass.config_entries.async_update_entry(entry, options=options, version=2)

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
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id) or {}
    bridge: TurziMqttBridge | None = data.get("bridge")
    if bridge is None:
        return

    bridge.update_config(
        exposed_entities=entry.options.get(CONF_EXPOSED_ENTITIES, []),
        included_domains=entry.options.get(CONF_INCLUDED_DOMAINS, DEFAULT_INCLUDED_DOMAINS),
        auto_add_new=entry.options.get(CONF_AUTO_ADD_NEW, DEFAULT_AUTO_ADD_NEW),
        never_expose=entry.options.get(CONF_NEVER_EXPOSE, []),
    )

    # Acknowledge the applied revision via retained availability (v1.1 §5),
    # and report effective exposure upstream when locally edited.
    await bridge.async_set_config_revision(entry.options.get(CONF_CONFIG_REVISION))
    cloud: TurziCloudSync | None = data.get("cloud")
    if cloud:
        cloud.schedule_register()

    async_dispatcher_send(hass, SIGNAL_CONFIG_UPDATED)

    _LOGGER.info(
        "Config updated for house '%s'",
        entry.data.get("house_id", "unknown"),
    )
