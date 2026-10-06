"""The flows behind the bridge page's three add buttons.

Each filter or exclusion is a subentry, so Home Assistant lists it as a row on
the bridge's page, with an edit button and a delete action, and gives each
type its own add button:

- «Agregar filtro de dominio»: the domain, then (if it has any) its device
  classes, as checkboxes. None ticked publishes the whole domain.
- «Agregar filtro de entidades»: entities searched for and added one by one,
  of any domain.
- «Agregar exclusión»: the same search, for entities never published.

Adding, editing or deleting one fires the entry's update listener, which is
what makes the bridge publish or clear at once (`_async_options_updated`).
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_AUTO_ADD_NEW,
    CONF_FILTER_SNAPSHOT,
    DEFAULT_AUTO_ADD_NEW,
    FILTER_DEVICE_CLASSES,
    FILTER_DOMAIN,
    FILTER_ENTITIES,
    SELECTABLE_DOMAINS,
    SUBENTRY_DOMAIN_FILTER,
)
from .scope import (
    class_names,
    device_classes_for,
    domain_filter_title,
    domain_names,
    entity_names,
    join_names,
    take_snapshot,
)


class _ExposureSubentryFlow(ConfigSubentryFlow):
    """What the three flows share: saving a new row or an edited one."""

    def _editing(self) -> bool:
        return self.source == SOURCE_RECONFIGURE

    def _save(self, title: str, data: dict[str, Any], unique_id: str | None) -> SubentryFlowResult:
        if self._editing():
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                title=title,
                data=data,
                unique_id=unique_id,
            )
        return self.async_create_entry(title=title, data=data, unique_id=unique_id)


class DomainFilterFlow(_ExposureSubentryFlow):
    """«Agregar filtro de dominio»: a domain, then its classes."""

    _domain: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self._domain_step("user", user_input, None)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        current = self._get_reconfigure_subentry().data.get(FILTER_DOMAIN)
        return await self._domain_step("reconfigure", user_input, current)

    async def _domain_step(
        self, step_id: str, user_input: dict[str, Any] | None, current: str | None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            domain = user_input.get(FILTER_DOMAIN)
            if not domain:
                errors[FILTER_DOMAIN] = "domain_required"
            elif self._domain_taken(domain):
                errors[FILTER_DOMAIN] = "domain_filter_exists"
            else:
                self._domain = domain
                if await device_classes_for(self.hass, domain):
                    return await self.async_step_classes()
                return await self._save_domain([])

        names = await domain_names(self.hass, SELECTABLE_DOMAINS)
        options = sorted(
            (SelectOptionDict(value=d, label=f"{names[d]} ({d})") for d in SELECTABLE_DOMAINS),
            key=lambda option: option["label"].casefold(),
        )
        # Optional, and checked above: Home Assistant fills a required list
        # with its first option, so one Submit would add whatever domain
        # happens to sort first.
        field = vol.Optional(FILTER_DOMAIN, default=current) if current else vol.Optional(FILTER_DOMAIN)
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {field: SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN))}
            ),
            errors=errors,
        )

    async def async_step_classes(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """The chosen domain's classes, as checkboxes; none ticked is the whole domain."""
        domain = self._domain
        assert domain is not None
        if user_input is not None:
            return await self._save_domain(list(user_input.get(FILTER_DEVICE_CLASSES) or []))

        classes = await device_classes_for(self.hass, domain)
        labels = await class_names(self.hass, domain, classes)
        options = sorted(
            (SelectOptionDict(value=c, label=labels[c]) for c in classes),
            key=lambda option: option["label"].casefold(),
        )
        ticked: list[str] = []
        if self._editing():
            subentry = self._get_reconfigure_subentry()
            if subentry.data.get(FILTER_DOMAIN) == domain:
                ticked = [c for c in subentry.data.get(FILTER_DEVICE_CLASSES) or [] if c in classes]
        return self.async_show_form(
            step_id="classes",
            data_schema=vol.Schema(
                {
                    vol.Optional(FILTER_DEVICE_CLASSES, default=ticked): SelectSelector(
                        SelectSelectorConfig(
                            options=options, multiple=True, mode=SelectSelectorMode.LIST
                        )
                    )
                }
            ),
            description_placeholders={"domain": (await domain_names(self.hass, [domain]))[domain]},
        )

    async def _save_domain(self, classes: list[str]) -> SubentryFlowResult:
        domain = self._domain
        assert domain is not None
        data = {FILTER_DOMAIN: domain, FILTER_DEVICE_CLASSES: classes}
        self._hold_snapshot_to(data)
        return self._save(await domain_filter_title(self.hass, domain, classes), data, domain)

    def _hold_snapshot_to(self, data: dict[str, Any]) -> None:
        """Retake the snapshot for the domain filters as they will be once saved.

        Only with automatic exposure off, where domain filters cover the
        snapshot and nothing else: a filter saved now covers what exists now.
        A deleted filter leaves its entities in the snapshot, which is
        harmless, since no filter matches them any more. Entity filters and
        exclusions do not touch it: they name their entities.
        """
        entry = self._get_entry()
        if entry.options.get(CONF_AUTO_ADD_NEW, DEFAULT_AUTO_ADD_NEW):
            return
        replaced = self._get_reconfigure_subentry().subentry_id if self._editing() else None
        filters = [
            dict(s.data)
            for s in entry.subentries.values()
            if s.subentry_type == SUBENTRY_DOMAIN_FILTER and s.subentry_id != replaced
        ] + [data]
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_FILTER_SNAPSHOT: take_snapshot(self.hass, filters)}
        )

    def _domain_taken(self, domain: str) -> bool:
        """Another row already filters this domain: edit that one instead."""
        own = self._get_reconfigure_subentry().subentry_id if self._editing() else None
        return any(
            s.subentry_type == SUBENTRY_DOMAIN_FILTER
            and s.data.get(FILTER_DOMAIN) == domain
            and s.subentry_id != own
            for s in self._get_entry().subentries.values()
        )


class EntityListFlow(_ExposureSubentryFlow):
    """Entities searched for and added one by one: an entity filter or an exclusion."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self._entities_step("user", user_input, [])

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        current = list(self._get_reconfigure_subentry().data.get(FILTER_ENTITIES) or [])
        return await self._entities_step("reconfigure", user_input, current)

    async def _entities_step(
        self, step_id: str, user_input: dict[str, Any] | None, current: list[str]
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            entities = list(dict.fromkeys(user_input.get(FILTER_ENTITIES) or []))
            if not entities:
                errors[FILTER_ENTITIES] = "no_entities"
            else:
                title = join_names(entity_names(self.hass, entities))
                return self._save(title, {FILTER_ENTITIES: entities}, None)
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(FILTER_ENTITIES, default=current): EntitySelector(
                        EntitySelectorConfig(multiple=True)
                    )
                }
            ),
            errors=errors,
        )


class EntityFilterFlow(EntityListFlow):
    """«Agregar filtro de entidades»."""


class ExclusionFlow(EntityListFlow):
    """«Agregar exclusión»."""
