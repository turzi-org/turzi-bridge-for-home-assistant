"""The turzi Bridge integration."""

from __future__ import annotations

import logging

from types import MappingProxyType

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.helpers.start import async_at_started

from .cloud import TurziCloudSync
from .const import (
    CONF_AUTO_ADD_NEW,
    CONF_BRIDGE_TOKEN,
    CONF_CONFIG_REVISION,
    CONF_FILTER_SNAPSHOT,
    CONF_MODE,
    DEFAULT_AUTO_ADD_NEW,
    DOMAIN,
    DOOR_AND_SAFETY_CLASSES,
    FILTER_DEVICE_CLASSES,
    FILTER_DOMAIN,
    FILTER_ENTITIES,
    LEGACY_BINARY_SENSOR_CLASSES,
    LEGACY_DEFAULT_INCLUDED_DOMAINS,
    LEGACY_EXPOSED_ENTITIES,
    LEGACY_INCLUDED_DOMAINS,
    LEGACY_NEVER_EXPOSE,
    SIGNAL_CONFIG_UPDATED,
    SUBENTRY_DOMAIN_FILTER,
    SUBENTRY_ENTITY_FILTER,
    SUBENTRY_EXCLUSION,
)
from .mqtt_bridge import TurziMqttBridge
from .scope import (
    blocked_of,
    domain_filter_title,
    entity_names,
    filters_of,
    join_names,
    scope_of,
    take_snapshot,
)

_LOGGER = logging.getLogger(__name__)

type TurziConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: TurziConfigEntry) -> bool:
    """Set up turzi Bridge from a config entry."""
    bridge = TurziMqttBridge.from_config_entry(hass, entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"bridge": bridge, "cloud": None}

    # Cloud-enrolled entries get the management plane: catalog registration
    # up (HTTPS) and remote exposure config down (catalog response + the
    # retained config/exposure topic).
    if entry.data.get(CONF_MODE) == "cloud" and entry.data.get(CONF_BRIDGE_TOKEN):
        # Reauth ends in async_update_reload_and_abort, so a fresh load is the
        # only signal we get that the installer acted on the unlink repair —
        # nothing else ever clears it, and it would sit there red over a bridge
        # that is publishing normally.
        #
        # If the bridge is in fact still unlinked, the catalog POST that
        # `start()` fires answers 401 and raises `token_revoked` instead, so
        # the installer still gets a repair. Note what that does NOT cover: a
        # 401 is the only path back: `config/unlink` is explicitly not retained
        # (PROTOCOL.md §Unlink Notice — a later enrollment on the same
        # namespace must not replay a stale goodbye), so MQTT will never
        # re-raise it, and if the API is simply unreachable the POST fails as a
        # ClientError with no retry. Unreachable API plus unlinked bridge is
        # therefore a silent reconnect loop with nothing in the UI.
        async_delete_issue(hass, DOMAIN, f"unlinked_{entry.entry_id}")

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
        # A reload landing before STARTED replaces this record while the stale
        # closure still holds the old bridge. Without the identity check that
        # bridge starts anyway — unreachable from hass.data, so nothing can ever
        # stop it — and then double-publishes every state, double-executes every
        # command, and clobbers the live bridge's published-entities ledger,
        # which is keyed by entry_id and is what the next connect reconciles
        # retained state against. A reload cannot use entry.state to tell the
        # two apart: HA reuses the same ConfigEntry object across a reload.
        record = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if record is None or record.get("bridge") is not bridge:
            return
        # An entry that holds its filters to a snapshot but has none yet (it
        # came through the migration) takes it now, when every integration has
        # written its states: taken earlier it would miss entities, and they
        # would stop being published.
        ensure_snapshot(hass, entry, bridge)
        await bridge.async_start()
        # Re-read instead of reusing the snapshot above. `async_start` awaits
        # real disk I/O (the retained-topic ledger), and an unload landing in
        # that window pops the record and calls `cloud.stop()`. Starting the
        # already-stopped object off the stale dict would re-register the
        # registry listener that `stop()` just released, with nothing left to
        # ever unsubscribe it.
        record = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if record is None or record.get("bridge") is not bridge:
            return
        cloud_sync = record.get("cloud")
        if cloud_sync:
            cloud_sync.start()

    # Unsubscribing on unload is the primary guard; the check above covers the
    # case async_at_started dispatches immediately and hands back a no-op unsub.
    entry.async_on_unload(async_at_started(hass, _start_bridge))

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    _LOGGER.info(
        "turzi Bridge set up for house '%s' — will connect after HA start",
        entry.data.get("house_id", "unknown"),
    )
    return True


def ensure_snapshot(hass: HomeAssistant, entry: TurziConfigEntry, bridge: TurziMqttBridge) -> None:
    """Take the snapshot of an entry that holds its filters to one but has none.

    That is an entry that came through the migration with automatic exposure
    off. It is called once every integration has written its states: taken
    earlier, the snapshot would miss entities, and they would stop being
    published.
    """
    if entry.options.get(CONF_AUTO_ADD_NEW, DEFAULT_AUTO_ADD_NEW):
        return
    if entry.options.get(CONF_FILTER_SNAPSHOT) is not None:
        return
    options = {**entry.options, CONF_FILTER_SNAPSHOT: take_snapshot(hass, filters_of(entry))}
    hass.config_entries.async_update_entry(entry, options=options)
    bridge.update_config(scope=scope_of(entry, options), never_expose=sorted(blocked_of(entry)))


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


async def async_remove_entry(hass: HomeAssistant, entry: TurziConfigEntry) -> None:
    """Clear repairs the entry raised — they outlive it, and nothing else drops them.

    Deliberately not done in async_unload_entry: that also runs on every reload
    and at HA shutdown, where dropping a legitimately raised repair leaves the
    installer with no trace of why the bridge stopped.
    """
    async_delete_issue(hass, DOMAIN, f"unlinked_{entry.entry_id}")
    async_delete_issue(hass, DOMAIN, f"token_revoked_{entry.entry_id}")


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
      is left for the v2 → v3 step, which turns it into domain filters.

    **v2 → v3 — exposure becomes subentries.**

    Domain filters, entity filters and exclusions are each a subentry, so Home
    Assistant lists them on the bridge's page with an add button per type and
    a delete action per row. The v2 keys translate without changing what is
    published:

    - every `included_domains` entry becomes a domain filter;
    - `exposed_entities` become one entity filter;
    - `never_expose` becomes one exclusion;
    - `included_binary_sensor_classes` (2.2, never released) becomes a
      binary_sensor domain filter with those classes;
    - `auto_add_new` stays. An entry with it off takes its snapshot at its
      first start (`ensure_snapshot`), so what it publishes today stays
      published.

    One thing is added on purpose, logged: unless the entry already includes
    binary sensors, it gains a binary_sensor filter for the door and
    life-safety classes (`DOOR_AND_SAFETY_CLASSES`), because the platform's
    open-door alert has no other input and could not ask for one (Santiago,
    2026-10-06; turzi-apps DEFERRED_WORK.md D54). Exclusions still win.

    A major version, because an older bridge cannot read subentries. This one
    refuses entries from a newer bridge rather than guess at them.
    """
    if entry.version > 3:
        _LOGGER.error(
            "turzi Bridge: '%s' was configured by a newer version of the bridge "
            "(entry version %s). Update the bridge instead of downgrading it.",
            entry.data.get("house_id", "unknown"),
            entry.version,
        )
        return False

    if entry.version == 1:
        options = dict(entry.options)
        pre_branch = CONF_MODE not in entry.data
        curated = LEGACY_EXPOSED_ENTITIES in options
        previous = options.get(LEGACY_INCLUDED_DOMAINS, LEGACY_DEFAULT_INCLUDED_DOMAINS)

        if pre_branch and curated:
            options[LEGACY_INCLUDED_DOMAINS] = []
            _LOGGER.warning(
                "turzi Bridge: '%s' upgraded to the new exposure model. Listed "
                "domains are now exposed wholesale, so the previous list (%s) "
                "was cleared to keep exposure exactly as it is today — the %d "
                "entities already chosen, nothing new. Re-add domains under "
                "Settings → Devices → turzi Bridge → Configure to expose them "
                "wholesale.",
                entry.data.get("house_id", "unknown"),
                ", ".join(sorted(previous)) or "none",
                len(options.get(LEGACY_EXPOSED_ENTITIES) or []),
            )

        hass.config_entries.async_update_entry(entry, options=options, version=2)

    if entry.version == 2:
        options, items = _subentries_from_v2(dict(entry.options))
        if not any(
            kind == SUBENTRY_DOMAIN_FILTER and data[FILTER_DOMAIN] == "binary_sensor"
            for kind, data in items
        ):
            items.append(
                (
                    SUBENTRY_DOMAIN_FILTER,
                    {FILTER_DOMAIN: "binary_sensor", FILTER_DEVICE_CLASSES: list(DOOR_AND_SAFETY_CLASSES)},
                )
            )
            _LOGGER.warning(
                "turzi Bridge: '%s' now publishes binary sensors of these device "
                "classes: %s. A door's contact is what the platform's open-door "
                "alert reads, and the rest are life-safety sensors. Delete that "
                "filter on the bridge's page under Settings → Devices & services, "
                "or add an exclusion for a specific sensor.",
                entry.data.get("house_id", "unknown"),
                ", ".join(DOOR_AND_SAFETY_CLASSES),
            )
        for kind, data in items:
            hass.config_entries.async_add_subentry(
                entry,
                ConfigSubentry(
                    data=MappingProxyType(data),
                    subentry_type=kind,
                    title=await _title(hass, kind, data),
                    unique_id=data[FILTER_DOMAIN] if kind == SUBENTRY_DOMAIN_FILTER else None,
                ),
            )
        hass.config_entries.async_update_entry(
            entry, options=options, version=3, minor_version=1
        )

    return True


def _subentries_from_v2(options: dict) -> tuple[dict, list[tuple[str, dict]]]:
    """The v2 exposure keys as subentries, and what is left of the options."""
    included = options.pop(LEGACY_INCLUDED_DOMAINS, LEGACY_DEFAULT_INCLUDED_DOMAINS) or []
    exposed = [e for e in options.pop(LEGACY_EXPOSED_ENTITIES, None) or [] if isinstance(e, str)]
    blocked = [e for e in options.pop(LEGACY_NEVER_EXPOSE, None) or [] if isinstance(e, str)]
    classes = options.pop(LEGACY_BINARY_SENSOR_CLASSES, None) or []
    # Keys of the label-based schema older still, if an entry kept them.
    for legacy_key in ("expose_label", "label_mode", "additional_entities", "excluded_entities"):
        options.pop(legacy_key, None)

    items: list[tuple[str, dict]] = [
        (SUBENTRY_DOMAIN_FILTER, {FILTER_DOMAIN: domain, FILTER_DEVICE_CLASSES: []})
        for domain in dict.fromkeys(included)
    ]
    if classes and "binary_sensor" not in included:
        items.append(
            (SUBENTRY_DOMAIN_FILTER, {FILTER_DOMAIN: "binary_sensor", FILTER_DEVICE_CLASSES: list(classes)})
        )
    if exposed:
        items.append((SUBENTRY_ENTITY_FILTER, {FILTER_ENTITIES: exposed}))
    if blocked:
        items.append((SUBENTRY_EXCLUSION, {FILTER_ENTITIES: blocked}))
    options.setdefault(CONF_AUTO_ADD_NEW, DEFAULT_AUTO_ADD_NEW)
    return options, items


async def _title(hass: HomeAssistant, kind: str, data: dict) -> str:
    """A subentry's row title, as the add flows word it."""
    if kind == SUBENTRY_DOMAIN_FILTER:
        return await domain_filter_title(hass, data[FILTER_DOMAIN], data[FILTER_DEVICE_CLASSES])
    return join_names(entity_names(hass, data[FILTER_ENTITIES]))


async def _async_options_updated(hass: HomeAssistant, entry: TurziConfigEntry) -> None:
    """Handle an options or subentry change — sync bridge config without a reload.

    Home Assistant runs this for every subentry added, edited or deleted, as
    well as for options, so a filter or exclusion applies the moment it is
    saved.
    """
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id) or {}
    bridge: TurziMqttBridge | None = data.get("bridge")
    if bridge is None:
        return

    bridge.update_config(scope=scope_of(entry), never_expose=sorted(blocked_of(entry)))

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
