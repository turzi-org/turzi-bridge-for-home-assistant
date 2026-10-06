"""What is in the bridge's publish scope.

One rule, used by everything that has to agree on it: publishing, retained
cleanup, command gating (`TurziMqttBridge.should_expose`) and the catalog
(`cloud.build_catalog`), which is the publish scope and nothing more.

Kept free of Home Assistant imports so the rule can be read, and tested, on
its own.
"""

from __future__ import annotations

from collections.abc import Collection


def in_publish_scope(
    entity_id: str,
    device_class: str | None,
    *,
    included_domains: Collection[str],
    exposed_entities: Collection[str],
    binary_sensor_classes: Collection[str],
) -> bool:
    """Whether an entity is included, before the privacy blocklist.

    Included when it is a manual addition, when its domain is included
    wholesale, or when it is a binary sensor of an included device class. The
    privacy blocklist (`never_expose`) is the caller's to apply: publishing
    drops a blocked entity, while the catalog still lists it, marked
    `locally_blocked`, so the platform can show why it is missing.

    `device_class` is the effective one, as Home Assistant writes it into the
    state's attributes: an override set under the entity's "Show as" wins over
    the integration's.
    """
    if entity_id in exposed_entities:
        return True
    domain = entity_id.split(".", 1)[0]
    if domain in included_domains:
        return True
    return (
        domain == "binary_sensor"
        and device_class is not None
        and device_class in binary_sensor_classes
    )
