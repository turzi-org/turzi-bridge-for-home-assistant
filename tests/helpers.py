"""Small doubles shared by the tests."""

from __future__ import annotations

from typing import Any

from custom_components.turzi_bridge.const import (
    CONF_AUTO_ADD_NEW,
    CONF_EXPOSED_ENTITIES,
    CONF_INCLUDED_BINARY_SENSOR_CLASSES,
    CONF_INCLUDED_DOMAINS,
    CONF_NEVER_EXPOSE,
    DEFAULT_INCLUDED_BINARY_SENSOR_CLASSES,
)

HOUSE = "house-1"


def cloud_options(**over: Any) -> dict[str, Any]:
    """Options as a cloud enrollment leaves them, binary_sensor not included."""
    return {
        CONF_INCLUDED_DOMAINS: ["light", "lock", "alarm_control_panel"],
        CONF_EXPOSED_ENTITIES: [],
        CONF_AUTO_ADD_NEW: True,
        CONF_NEVER_EXPOSE: [],
        CONF_INCLUDED_BINARY_SENSOR_CLASSES: list(DEFAULT_INCLUDED_BINARY_SENSOR_CLASSES),
        **over,
    }


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
