"""The config entry is titled after its community and organization, not a house id (#1160).

And the «Turzi Stack address» field refuses anything but a bare IP, saying why.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.turzi_bridge.cloud import TurziCloudSync
from custom_components.turzi_bridge.const import DOMAIN, CONF_API_ADDRESS, CONF_API_BASE_URL
from custom_components.turzi_bridge.enrollment import entry_title
from custom_components.turzi_bridge.mqtt_bridge import TurziMqttBridge

from .helpers import bridge_entry, domain_filter
from .test_refresh import ADDRESS, BEFORE, BY_ADDRESS, BY_NAME, NOW, _to_refresh

NAMES = {"community": "Dev Smoke Test", "organization": "Turzi"}
TITLE = "Turzi · Dev Smoke Test (Turzi)"


def test_the_title_names_the_community_and_its_organization() -> None:
    assert entry_title(NAMES) == TITLE
    assert entry_title({"community": " Dev Smoke Test ", "organization": None}) == "Turzi · Dev Smoke Test"
    # An older platform sends no names, or no community: the entry keeps its title.
    assert entry_title(None) is None
    assert entry_title({"community": "", "organization": "Turzi"}) is None
    assert entry_title("Dev Smoke Test") is None


async def test_finding_the_connection_again_titles_the_entry(hass: HomeAssistant, aioclient_mock) -> None:
    entry = bridge_entry(hass, domain_filter("lock"), data=dict(BEFORE))
    aioclient_mock.get(f"{BY_ADDRESS}/bridge/connection", json={**NOW, "names": NAMES})
    result = await _to_refresh(hass, entry)
    with patch("custom_components.turzi_bridge.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_BASE_URL: BY_NAME, CONF_API_ADDRESS: ADDRESS})
        await hass.async_block_till_done()
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "refresh_successful")
    assert entry.title == TITLE


async def test_with_no_names_the_title_stays(hass: HomeAssistant, aioclient_mock) -> None:
    entry = bridge_entry(hass, domain_filter("lock"), data=dict(BEFORE))
    before = entry.title
    aioclient_mock.get(f"{BY_ADDRESS}/bridge/connection", json=NOW)
    result = await _to_refresh(hass, entry)
    with patch("custom_components.turzi_bridge.async_setup_entry", return_value=True):
        await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_BASE_URL: BY_NAME, CONF_API_ADDRESS: ADDRESS})
        await hass.async_block_till_done()
    assert entry.title == before


async def test_a_url_as_the_stack_address_is_refused_and_nothing_is_asked(hass: HomeAssistant, aioclient_mock) -> None:
    entry = bridge_entry(hass, domain_filter("lock"), data=dict(BEFORE))
    result = await _to_refresh(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_BASE_URL: BY_NAME, CONF_API_ADDRESS: f"http://{ADDRESS}:8126/api/v2"}
    )
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "refresh"
    assert result["errors"] == {CONF_API_ADDRESS: "address_not_ip"}
    assert aioclient_mock.call_count == 0
    assert entry.data == BEFORE


async def test_a_refused_login_titles_the_entry_even_when_the_connection_is_the_same(hass: HomeAssistant, aioclient_mock) -> None:
    entry = bridge_entry(hass, domain_filter("lock"), data=dict(BEFORE))
    with patch.object(TurziMqttBridge, "async_start", AsyncMock()), patch("custom_components.turzi_bridge.TurziCloudSync.start"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    bridge = hass.data[DOMAIN][entry.entry_id]["bridge"]
    same = {"mqtt": {"host": ADDRESS, "port": 1883, "tls": False, "username": "bridge-house-1", "password": "old"}, "names": NAMES}
    aioclient_mock.get(f"{BEFORE[CONF_API_BASE_URL]}/bridge/connection", json=same)
    with patch.object(hass.config_entries, "async_schedule_reload", MagicMock()) as reload:
        await bridge.connection_refused_callback()
    assert entry.title == TITLE
    reload.assert_not_called()


async def test_the_catalog_answer_titles_the_entry_so_a_rename_arrives_at_start(hass: HomeAssistant, aioclient_mock) -> None:
    entry = bridge_entry(hass, domain_filter("lock"), data=dict(BEFORE))
    aioclient_mock.post(f"{BEFORE[CONF_API_BASE_URL]}/bridge/catalog", json={"exposure": None, "names": {**NAMES, "community": "Dev Smoke Test 2"}})
    await TurziCloudSync(hass, entry).async_register_catalog()
    assert entry.title == "Turzi · Dev Smoke Test 2 (Turzi)"
