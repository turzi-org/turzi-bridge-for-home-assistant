"""Turzi Cloud sync: catalog registration and remote exposure config.

Implements the management plane for cloud-enrolled bridges:
- Catalog up via HTTPS (BRIDGE_CLOUD_API.md §3): the full candidate-entity
  inventory, POSTed with the bridge token. Never transits MQTT — it lists
  unexposed entities and must not be readable by house clients.
- Exposure config down (PROTOCOL.md, Exposure Configuration): applied from
  the catalog response here, and from the retained config/exposure MQTT
  topic via TurziMqttBridge.

Manual/self-hosted entries never use this module.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

import aiohttp

from homeassistant.const import __version__ as HA_VERSION
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_integration
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)

from .const import (
    CONF_API_BASE_URL,
    CONF_AUTO_ADD_NEW,
    CONF_BRIDGE_TOKEN,
    CONF_CONFIG_REVISION,
    CONF_EXPOSED_ENTITIES,
    CONF_INCLUDED_DOMAINS,
    CONF_NEVER_EXPOSE,
    DOMAIN,
    PROTOCOL_VERSION,
    SELECTABLE_DOMAINS,
)

_LOGGER = logging.getLogger(__name__)

CATALOG_DEBOUNCE_SECONDS = 10
CATALOG_TIMEOUT = aiohttp.ClientTimeout(total=30)
CAPABILITIES = ["remote_config"]


def build_catalog(hass: HomeAssistant, entry: ConfigEntry) -> list[dict[str, Any]]:
    """Build the entity catalog: the bridge's actual publish scope.

    Only entities in the included domains plus individually exposed
    entities (added via the options flow) are reported — the platform
    never sees unwanted entities, and everything in the catalog is
    published (unless locally blocked).
    """
    exposed = set(entry.options.get(CONF_EXPOSED_ENTITIES, []))
    blocked = set(entry.options.get(CONF_NEVER_EXPOSE, []))
    included = set(entry.options.get(CONF_INCLUDED_DOMAINS, []))

    registry = er.async_get(hass)
    entities: list[dict[str, Any]] = []
    for reg_entry in registry.entities.values():
        if reg_entry.disabled_by:
            continue
        if reg_entry.domain not in included and reg_entry.entity_id not in exposed:
            continue
        state = hass.states.get(reg_entry.entity_id)
        name = (
            reg_entry.name
            or reg_entry.original_name
            or (state.name if state else None)
            or reg_entry.entity_id
        )
        created_at = getattr(reg_entry, "created_at", None)
        entities.append(
            {
                "id": reg_entry.entity_id,
                "domain": reg_entry.domain,
                "slug": reg_entry.entity_id.split(".", 1)[1],
                "name": name,
                "area": reg_entry.area_id,
                "device_class": (
                    state.attributes.get("device_class") if state else None
                ),
                "exposed": reg_entry.entity_id not in blocked,
                "locally_blocked": reg_entry.entity_id in blocked,
                "last_seen": state.last_updated.isoformat() if state else None,
                "added_on": created_at.isoformat() if created_at else None,
            }
        )
    entities.sort(key=lambda e: e["id"])
    return entities


class TurziCloudSync:
    """Catalog registration + exposure application for a cloud entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._debounce_task: asyncio.Task | None = None
        self._last_hash: str | None = None
        self._unsub_registry: callback | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start(self) -> None:
        """Register the catalog now and on future registry changes."""
        self.hass.async_create_task(
            self.async_register_catalog(), "turzi_cloud_catalog_initial"
        )

        @callback
        def _on_registry_updated(_event) -> None:
            self.schedule_register()

        self._unsub_registry = self.hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED, _on_registry_updated
        )

    def stop(self) -> None:
        if self._unsub_registry:
            self._unsub_registry()
            self._unsub_registry = None
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

    def schedule_register(self) -> None:
        """Debounced catalog re-registration."""
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        async def _debounced() -> None:
            await asyncio.sleep(CATALOG_DEBOUNCE_SECONDS)
            await self.async_register_catalog()

        self._debounce_task = self.hass.async_create_task(
            _debounced(), "turzi_cloud_catalog_debounced"
        )

    # ── Catalog registration ─────────────────────────────────────────────

    async def async_register_catalog(self) -> None:
        """POST the catalog; apply the exposure config from the response."""
        token = self.entry.data.get(CONF_BRIDGE_TOKEN)
        base_url = self.entry.data.get(CONF_API_BASE_URL)
        if not token or not base_url:
            return

        entities = build_catalog(self.hass, self.entry)
        integration = await async_get_integration(self.hass, DOMAIN)
        payload = {
            "catalog_hash": "sha256:"
            + hashlib.sha256(
                json.dumps(entities, sort_keys=True).encode()
            ).hexdigest(),
            "protocol_version": PROTOCOL_VERSION,
            "bridge_version": integration.version and str(integration.version),
            "core_version": HA_VERSION,
            "capabilities": CAPABILITIES,
            "applied_config_revision": self.entry.options.get(CONF_CONFIG_REVISION),
            "entities": entities,
        }
        if payload["catalog_hash"] == self._last_hash:
            return

        session = async_get_clientsession(self.hass)
        url = f"{base_url.rstrip('/')}/bridge/catalog"
        try:
            async with session.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=CATALOG_TIMEOUT,
            ) as resp:
                if resp.status == 401:
                    _LOGGER.error("Bridge token revoked — re-enrollment required")
                    async_create_issue(
                        self.hass,
                        DOMAIN,
                        f"token_revoked_{self.entry.entry_id}",
                        is_fixable=False,
                        severity=IssueSeverity.ERROR,
                        translation_key="token_revoked",
                    )
                    self.entry.async_start_reauth(self.hass)
                    return
                if resp.status != 200:
                    _LOGGER.warning("Catalog registration failed: HTTP %s", resp.status)
                    return
                body = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.warning("Catalog registration failed: %s", err)
            return

        self._last_hash = payload["catalog_hash"]
        async_delete_issue(self.hass, DOMAIN, f"token_revoked_{self.entry.entry_id}")
        _LOGGER.debug("Catalog registered (%d entities)", len(entities))

        exposure = body.get("exposure")
        if exposure:
            await self.async_apply_exposure(exposure)

    # ── Exposure application ─────────────────────────────────────────────

    async def async_apply_exposure(self, exposure: dict[str, Any]) -> None:
        """Apply a platform exposure revision (from catalog response or MQTT).

        Revision replay protection, local blocklist supremacy, and retained-
        state cleanup all follow PROTOCOL.md (Exposure Configuration). The
        options update propagates to the running bridge via the existing
        update listener, which also handles state publish/cleanup diffs.
        """
        revision = exposure.get("revision")
        entities = exposure.get("entities")
        if not isinstance(revision, int) or not isinstance(entities, list):
            _LOGGER.warning("Ignoring malformed exposure config")
            return

        current = self.entry.options.get(CONF_CONFIG_REVISION) or 0
        if revision <= current:
            _LOGGER.debug(
                "Ignoring exposure revision %s (applied: %s)", revision, current
            )
            return

        blocked = set(self.entry.options.get(CONF_NEVER_EXPOSE, []))
        effective = [e for e in entities if isinstance(e, str) and e not in blocked]
        auto_add = [
            d
            for d in exposure.get("auto_add_domains", [])
            if isinstance(d, str) and d in SELECTABLE_DOMAINS
        ]

        new_options = {
            **self.entry.options,
            CONF_EXPOSED_ENTITIES: effective,
            CONF_INCLUDED_DOMAINS: auto_add,
            CONF_AUTO_ADD_NEW: bool(auto_add),
            CONF_CONFIG_REVISION: revision,
        }
        self.hass.config_entries.async_update_entry(self.entry, options=new_options)
        _LOGGER.info(
            "Applied exposure revision %s (%d entities, %d blocked locally)",
            revision,
            len(effective),
            len(entities) - len(effective),
        )
        # Report effective exposure (and the applied revision) back upstream.
        self.schedule_register()
