"""Finding the connection again with the bridge's own token, and no key (config_flow `refresh`)."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.turzi_bridge.const import (
    CONF_API_ADDRESS,
    CONF_API_BASE_URL,
    CONF_BRIDGE_TOKEN,
    CONF_BROKER,
    CONF_HOUSE_ID,
    CONF_PORT,
    CONF_TLS_SERVER_NAME,
    CONF_USE_TLS,
)

from .helpers import bridge_entry, domain_filter

NAME = "k7q2m9xw3d.stack.turzi.cloud"
ADDRESS = "10.0.0.5"
BY_NAME = f"https://{NAME}:8126/api/v2"
BY_ADDRESS = f"https://{ADDRESS}:8126/api/v2"
# A bridge enrolled when the building's Stack still served in clear.
BEFORE = {
    "mode": "cloud", CONF_HOUSE_ID: "house-1", CONF_BRIDGE_TOKEN: "token-1", CONF_BROKER: ADDRESS, CONF_PORT: 1883, CONF_USE_TLS: False,
    "username": "bridge-house-1", "password": "old", CONF_API_BASE_URL: f"http://{ADDRESS}:8126/api/v2",
}
NOW = {
    "mqtt": {"host": ADDRESS, "port": 8883, "tls": True, "tls_server_name": NAME, "username": "bridge-house-1", "password": "new"},
    "api": {"base_url": BY_NAME, "address": ADDRESS},
}


async def _to_refresh(hass: HomeAssistant, entry):
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.MENU and result["step_id"] == "reconfigure_how"
    # Without a key first: that is the one that spends nothing.
    assert result["menu_options"] == ["refresh", "reconfigure_cloud"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "refresh"})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "refresh"
    return result


async def test_the_bridge_finds_its_broker_again_with_its_own_token(hass: HomeAssistant, aioclient_mock) -> None:
    entry = bridge_entry(hass, domain_filter("lock"), data=dict(BEFORE))
    aioclient_mock.get(f"{BY_ADDRESS}/bridge/connection", json=NOW)
    result = await _to_refresh(hass, entry)
    with patch("custom_components.turzi_bridge.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_BASE_URL: BY_NAME, CONF_API_ADDRESS: ADDRESS})
        await hass.async_block_till_done()
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "refresh_successful")
    (_method, url, _data, headers), = aioclient_mock.mock_calls
    assert str(url) == f"{BY_ADDRESS}/bridge/connection" and headers["Authorization"] == "Bearer token-1"
    data = entry.data
    assert (data[CONF_BROKER], data[CONF_PORT], data[CONF_USE_TLS], data[CONF_TLS_SERVER_NAME]) == (ADDRESS, 8883, True, NAME)
    assert (data[CONF_API_BASE_URL], data[CONF_API_ADDRESS], data["password"]) == (BY_NAME, ADDRESS, "new")
    # Who it is did not change: nothing was enrolled.
    assert (data[CONF_HOUSE_ID], data[CONF_BRIDGE_TOKEN], data["mode"]) == ("house-1", "token-1", "cloud")


async def test_a_bridge_the_api_no_longer_knows_is_told_so_and_left_as_it_was(hass: HomeAssistant, aioclient_mock) -> None:
    entry = bridge_entry(hass, domain_filter("lock"), data=dict(BEFORE))
    aioclient_mock.get(f"{BY_ADDRESS}/bridge/connection", status=401, json={"error": "token_revoked"})
    result = await _to_refresh(hass, entry)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_BASE_URL: BY_NAME, CONF_API_ADDRESS: ADDRESS})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "token_revoked"}
    assert dict(entry.data) == BEFORE


async def test_a_stack_still_preparing_its_certificate_says_to_wait(hass: HomeAssistant, aioclient_mock) -> None:
    entry = bridge_entry(hass, domain_filter("lock"), data=dict(BEFORE))
    aioclient_mock.get(f"{BY_ADDRESS}/bridge/connection", status=409, json={"error": "building_tls_pending"})
    result = await _to_refresh(hass, entry)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_BASE_URL: BY_NAME, CONF_API_ADDRESS: ADDRESS})
    assert result["errors"] == {"base": "building_tls_pending"} and dict(entry.data) == BEFORE
