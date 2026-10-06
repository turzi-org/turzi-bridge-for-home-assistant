"""Small doubles shared by the tests."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigSubentryData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.turzi_bridge.const import (
    CONF_AUTO_ADD_NEW,
    DOMAIN,
    DOOR_AND_SAFETY_CLASSES,
    FILTER_DEVICE_CLASSES,
    FILTER_DOMAIN,
    FILTER_ENTITIES,
    SUBENTRY_DOMAIN_FILTER,
    SUBENTRY_ENTITY_FILTER,
    SUBENTRY_EXCLUSION,
)

HOUSE = "house-1"


def domain_filter(domain: str, classes: list[str] | None = None) -> ConfigSubentryData:
    return ConfigSubentryData(
        data={FILTER_DOMAIN: domain, FILTER_DEVICE_CLASSES: list(classes or [])},
        subentry_type=SUBENTRY_DOMAIN_FILTER,
        title=domain,
        unique_id=domain,
    )


def entity_filter(*entities: str) -> ConfigSubentryData:
    return ConfigSubentryData(
        data={FILTER_ENTITIES: list(entities)}, subentry_type=SUBENTRY_ENTITY_FILTER, title="entities", unique_id=None
    )


def exclusion(*entities: str) -> ConfigSubentryData:
    return ConfigSubentryData(
        data={FILTER_ENTITIES: list(entities)}, subentry_type=SUBENTRY_EXCLUSION, title="excluded", unique_id=None
    )


def door_and_safety() -> ConfigSubentryData:
    return domain_filter("binary_sensor", list(DOOR_AND_SAFETY_CLASSES))


def bridge_entry(hass, *subentries: ConfigSubentryData, options: dict[str, Any] | None = None, data=None) -> MockConfigEntry:
    """A current (v3) entry with these rows, added to hass."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        minor_version=1,
        data=data or {"mode": "cloud", "house_id": HOUSE, "broker": "localhost", "port": 1883, "use_tls": False},
        options={CONF_AUTO_ADD_NEW: True, **(options or {})},
        subentries_data=list(subentries),
    )
    entry.add_to_hass(hass)
    return entry


class FakeClient:
    """Records what the bridge publishes instead of reaching a broker."""

    def __init__(self) -> None:
        self.publishes: list[tuple[str, Any, bool]] = []

    async def publish(self, topic: str, payload: Any = None, qos: int = 0, retain: bool = False) -> None:
        self.publishes.append((topic, payload, retain))

    def cleared(self, entity_id: str) -> bool:
        domain, slug = entity_id.split(".", 1)
        return (f"house/{HOUSE}/state/{domain}/{slug}", "", True) in self.publishes

    def published(self, entity_id: str) -> bool:
        domain, slug = entity_id.split(".", 1)
        topic = f"house/{HOUSE}/state/{domain}/{slug}"
        return any(t == topic and p not in ("", None) for t, p, _ in self.publishes)
