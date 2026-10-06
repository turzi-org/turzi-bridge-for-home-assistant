"""A platform exposure revision replaces the filter rows and keeps the exclusions."""

from homeassistant.core import HomeAssistant

from custom_components.turzi_bridge.cloud import TurziCloudSync
from custom_components.turzi_bridge.const import CONF_AUTO_ADD_NEW, CONF_CONFIG_REVISION

from .helpers import bridge_entry, domain_filter, exclusion


async def test_a_revision_becomes_filter_rows(hass: HomeAssistant) -> None:
    entry = bridge_entry(hass, domain_filter("light"), exclusion("lock.servicio"))
    sync = TurziCloudSync(hass, entry)
    sync.schedule_register = lambda: None

    await sync.async_apply_exposure(
        {"revision": 3, "entities": ["switch.bomba", "lock.servicio"], "auto_add_domains": ["climate"]}
    )

    rows = sorted((s.subentry_type, dict(s.data)) for s in entry.subentries.values())
    assert rows == sorted([
        ("domain_filter", {"domain": "climate", "device_classes": []}),
        ("entity_filter", {"entities": ["switch.bomba"]}),
        ("exclusion", {"entities": ["lock.servicio"]}),
    ])
    assert entry.options[CONF_CONFIG_REVISION] == 3 and entry.options[CONF_AUTO_ADD_NEW] is True


async def test_an_old_revision_is_ignored(hass: HomeAssistant) -> None:
    entry = bridge_entry(hass, domain_filter("light"), options={CONF_CONFIG_REVISION: 5})
    sync = TurziCloudSync(hass, entry)

    await sync.async_apply_exposure({"revision": 5, "entities": [], "auto_add_domains": []})

    assert [s.unique_id for s in entry.subentries.values()] == ["light"]
