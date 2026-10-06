"""What is in the bridge's publish scope.

One rule, used by everything that has to agree on it: publishing, retained
cleanup, command gating (`TurziMqttBridge.should_expose`), the catalog
(`cloud.build_catalog`), which is the publish scope and nothing more, and the
snapshot that domain and class filters are held to when new entities are not
added by themselves.

Kept free of Home Assistant imports so the rule can be read, and tested, on
its own.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .const import FILTER_DEVICE_CLASSES, FILTER_DOMAIN, FILTER_ENTITIES


@dataclass(frozen=True)
class PublishScope:
    """The filters, compiled so that a state change costs a few set lookups.

    Two kinds of filter (`scope.filters_of` reads them from the subentries):

    - a domain filter: every entity of the domain, or only those with one of
      its device classes, as Home Assistant reports it (an installer's "Show
      as" wins over the integration's class);
    - an entity filter: the entities it names, of any domain.

    With `auto_add_new` off, domain filters cover only the entities in
    `snapshot`, which is taken each time a filter is saved; entity filters
    name their entities and do not depend on it.

    Exclusions are the caller's to apply: publishing drops an excluded
    entity, while the catalog still lists it, marked `locally_blocked`.
    """

    wholesale: frozenset[str]
    classes: Mapping[str, frozenset[str]]
    entities: frozenset[str]
    auto_add_new: bool = True
    snapshot: frozenset[str] = frozenset()

    @classmethod
    def from_filters(
        cls,
        filters: Iterable[Mapping[str, Any]] | None,
        *,
        auto_add_new: bool = True,
        snapshot: Iterable[str] | None = None,
    ) -> PublishScope:
        wholesale: set[str] = set()
        classes: dict[str, set[str]] = {}
        entities: set[str] = set()
        for item in filters or ():
            if not isinstance(item, Mapping):
                continue
            named = [e for e in item.get(FILTER_ENTITIES) or () if isinstance(e, str)]
            if named:
                entities.update(named)
                continue
            domain = item.get(FILTER_DOMAIN)
            if not isinstance(domain, str) or not domain:
                continue
            listed = [c for c in item.get(FILTER_DEVICE_CLASSES) or () if isinstance(c, str)]
            if listed:
                classes.setdefault(domain, set()).update(listed)
            else:
                wholesale.add(domain)
        return cls(
            wholesale=frozenset(wholesale),
            classes={domain: frozenset(c) for domain, c in classes.items()},
            entities=frozenset(entities),
            auto_add_new=auto_add_new,
            snapshot=frozenset(snapshot or ()),
        )

    def needs_device_class(self, entity_id: str) -> bool:
        """Whether the answer depends on the entity's device class."""
        domain = entity_id.split(".", 1)[0]
        return domain in self.classes and domain not in self.wholesale

    def matches_filter(self, entity_id: str, device_class: str | None) -> bool:
        """Matched by a domain filter: what a snapshot records."""
        domain = entity_id.split(".", 1)[0]
        if domain in self.wholesale:
            return True
        listed = self.classes.get(domain)
        return listed is not None and device_class is not None and device_class in listed

    def includes(self, entity_id: str, device_class: str | None) -> bool:
        """Whether the entity is in the publish scope, before the blocklist."""
        if entity_id in self.entities:
            return True
        if not self.matches_filter(entity_id, device_class):
            return False
        return self.auto_add_new or entity_id in self.snapshot
