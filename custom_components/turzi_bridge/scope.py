"""The publish scope, read from an entry and measured against Home Assistant.

`exposure.PublishScope` is the rule. This module reads it from the entry's
subentries (domain filters, entity filters, exclusions), walks the entities it
applies to, and words what the flows show. The catalog, the snapshot and the
flows' counts all go through `candidates()`, so they cannot disagree about
which entities exist or what class each one is.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.importlib import async_import_module
from homeassistant.helpers.translation import async_get_translations

from .const import (
    CONF_AUTO_ADD_NEW,
    CONF_FILTER_SNAPSHOT,
    DEFAULT_AUTO_ADD_NEW,
    FILTER_ENTITIES,
    SUBENTRY_DOMAIN_FILTER,
    SUBENTRY_ENTITY_FILTER,
    SUBENTRY_EXCLUSION,
)
from .exposure import PublishScope

# The domains with device classes, and the enum Home Assistant defines them in.
# The class screen offers exactly these, so a class it lists always exists.
DEVICE_CLASS_ENUMS: dict[str, tuple[str, str]] = {
    "binary_sensor": ("homeassistant.components.binary_sensor", "BinarySensorDeviceClass"),
    "button": ("homeassistant.components.button", "ButtonDeviceClass"),
    "cover": ("homeassistant.components.cover", "CoverDeviceClass"),
    "humidifier": ("homeassistant.components.humidifier", "HumidifierDeviceClass"),
    "media_player": ("homeassistant.components.media_player", "MediaPlayerDeviceClass"),
    "number": ("homeassistant.components.number", "NumberDeviceClass"),
    "sensor": ("homeassistant.components.sensor", "SensorDeviceClass"),
    "switch": ("homeassistant.components.switch", "SwitchDeviceClass"),
    "valve": ("homeassistant.components.valve", "ValveDeviceClass"),
}


@dataclass(frozen=True)
class Candidate:
    """An entity the filters could apply to."""

    entity_id: str
    device_class: str | None
    registry_entry: er.RegistryEntry | None
    state: State | None


# ── Reading the entry ─────────────────────────────────────────────────────


def filters_of(entry: ConfigEntry) -> list[dict[str, Any]]:
    """The entry's domain and entity filters, as `PublishScope` reads them."""
    filters: list[dict[str, Any]] = []
    for subentry in entry.subentries.values():
        if subentry.subentry_type in (SUBENTRY_DOMAIN_FILTER, SUBENTRY_ENTITY_FILTER):
            filters.append(dict(subentry.data))
    return filters


def blocked_of(entry: ConfigEntry) -> set[str]:
    """Every entity an exclusion names."""
    blocked: set[str] = set()
    for subentry in entry.subentries.values():
        if subentry.subentry_type == SUBENTRY_EXCLUSION:
            blocked.update(e for e in subentry.data.get(FILTER_ENTITIES) or () if isinstance(e, str))
    return blocked


def scope_of(entry: ConfigEntry, options: Mapping[str, Any] | None = None) -> PublishScope:
    """The entry's filters, compiled. `options` overrides the entry's own."""
    opts = entry.options if options is None else options
    return PublishScope.from_filters(
        filters_of(entry),
        auto_add_new=opts.get(CONF_AUTO_ADD_NEW, DEFAULT_AUTO_ADD_NEW),
        snapshot=opts.get(CONF_FILTER_SNAPSHOT) or (),
    )


# ── Measuring against Home Assistant ──────────────────────────────────────


def candidates(hass: HomeAssistant) -> Iterator[Candidate]:
    """Every enabled registry entity, then every unregistered state.

    The second walk is there because YAML `group:` entities and template or
    command_line entities declared without a unique_id never get a registry
    entry, yet they publish and accept commands. Their registry lookup also
    keeps a disabled entity whose state has not been torn down yet from coming
    back in.

    The device class is the effective one: the state carries an installer's
    "Show as" override over the integration's class, and without a state the
    registry holds the same two, in the same order.
    """
    registry = er.async_get(hass)
    for entry in registry.entities.values():
        if entry.disabled_by:
            continue
        state = hass.states.get(entry.entity_id)
        device_class = (
            state.attributes.get("device_class")
            if state
            else (entry.device_class or entry.original_device_class)
        )
        yield Candidate(entry.entity_id, device_class, entry, state)
    for state in hass.states.async_all():
        if registry.async_get(state.entity_id) is not None:
            continue
        yield Candidate(state.entity_id, state.attributes.get("device_class"), None, state)


def take_snapshot(hass: HomeAssistant, filters: Iterable[Mapping[str, Any]]) -> list[str]:
    """The entities the domain filters match right now."""
    scope = PublishScope.from_filters(filters)
    return sorted(
        c.entity_id for c in candidates(hass) if scope.matches_filter(c.entity_id, c.device_class)
    )


def count_published(
    hass: HomeAssistant, filters: Iterable[Mapping[str, Any]], blocked: set[str]
) -> tuple[int, int]:
    """(published, held back by an exclusion) if the filters were saved now."""
    scope = PublishScope.from_filters(filters)
    published = held = 0
    for c in candidates(hass):
        if not scope.includes(c.entity_id, c.device_class):
            continue
        if c.entity_id in blocked:
            held += 1
        else:
            published += 1
    return published, held


# ── Words for the flows ───────────────────────────────────────────────────


async def device_classes_for(hass: HomeAssistant, domain: str) -> list[str]:
    """The device classes Home Assistant defines for a domain; [] for none."""
    where = DEVICE_CLASS_ENUMS.get(domain)
    if where is None:
        return []
    module = await async_import_module(hass, where[0])
    return [member.value for member in getattr(module, where[1])]


async def domain_names(hass: HomeAssistant, domains: Iterable[str]) -> dict[str, str]:
    """Each domain's name in Home Assistant's language, as Home Assistant words it."""
    domains = list(domains)
    titles = await async_get_translations(hass, hass.config.language, "title", domains)
    return {d: titles.get(f"component.{d}.title") or d for d in domains}


async def class_names(hass: HomeAssistant, domain: str, classes: Iterable[str]) -> dict[str, str]:
    """Each device class's name in Home Assistant's language."""
    classes = list(classes)
    words = await async_get_translations(hass, hass.config.language, "entity_component", [domain])
    return {
        c: words.get(f"component.{domain}.entity_component.{c}.name") or c.replace("_", " ")
        for c in classes
    }


def entity_names(hass: HomeAssistant, entity_ids: Iterable[str]) -> list[str]:
    """Each entity's name as Home Assistant shows it, else its id."""
    registry = er.async_get(hass)
    names: list[str] = []
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        entry = registry.async_get(entity_id)
        name = (
            (entry.name or entry.original_name) if entry else None
        ) or (state.name if state else None) or entity_id
        names.append(str(name))
    return names


def join_names(names: list[str], limit: int = 3) -> str:
    """"A, B, C" or "A, B, C +2": a row title stays one line."""
    if len(names) <= limit:
        return ", ".join(names)
    return f"{', '.join(names[:limit])} +{len(names) - limit}"


async def domain_filter_title(hass: HomeAssistant, domain: str, classes: list[str]) -> str:
    """"Luz", or "Sensor binario: Puerta, Ventana +6"."""
    name = (await domain_names(hass, [domain]))[domain]
    if not classes:
        return name
    labels = await class_names(hass, domain, classes)
    return f"{name}: {join_names([labels[c] for c in classes])}"
