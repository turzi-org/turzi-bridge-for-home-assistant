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


# --- A refused login, found again with nobody at the keyboard -----------------------------------------------------

import asyncio
from unittest.mock import AsyncMock, MagicMock

import aiomqtt
from aiomqtt.exceptions import MqttConnectError
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode

from custom_components.turzi_bridge.const import DOMAIN
from custom_components.turzi_bridge.mqtt_bridge import TurziMqttBridge, _login_refused, _unreachable

# Still in clear, as BEFORE: only the password moved (a connector enrolled again).
SAME_PLACE_NEW_PASSWORD = {
    "mqtt": {"host": ADDRESS, "port": 1883, "tls": False, "username": "bridge-house-1", "password": "new"},
}


def test_only_a_refused_login_counts_as_one() -> None:
    assert _login_refused(MqttConnectError(ReasonCode(PacketTypes.CONNACK, identifier=135)))
    assert _login_refused(MqttConnectError(ReasonCode(PacketTypes.CONNACK, identifier=134)))
    assert _login_refused(MqttConnectError(5)) and _login_refused(MqttConnectError(4))
    # A broker that is down or busy is not a login problem: nothing is asked.
    assert not _login_refused(MqttConnectError(ReasonCode(PacketTypes.CONNACK, identifier=136)))
    assert not _login_refused(aiomqtt.MqttCodeError(5, "Could not subscribe"))
    assert not _login_refused(aiomqtt.MqttError("[Errno 61] Connection refused"))


async def _set_up(hass: HomeAssistant, data: dict):
    entry = bridge_entry(hass, domain_filter("lock"), data=data)
    with patch.object(TurziMqttBridge, "async_start", AsyncMock()), patch("custom_components.turzi_bridge.TurziCloudSync.start"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry, hass.data[DOMAIN][entry.entry_id]["bridge"]


async def test_a_refused_login_asks_turzi_and_reconnects_with_the_new_one(hass: HomeAssistant, aioclient_mock) -> None:
    entry, bridge = await _set_up(hass, dict(BEFORE))
    aioclient_mock.get(f"{BEFORE[CONF_API_BASE_URL]}/bridge/connection", json=SAME_PLACE_NEW_PASSWORD)
    with patch.object(hass.config_entries, "async_schedule_reload", MagicMock()) as reload:
        await bridge.connection_refused_callback()
    (_method, _url, _data, headers), = aioclient_mock.mock_calls
    assert headers["Authorization"] == "Bearer token-1"
    assert entry.data["password"] == "new" and entry.data[CONF_BROKER] == ADDRESS
    assert (entry.data[CONF_HOUSE_ID], entry.data[CONF_BRIDGE_TOKEN]) == ("house-1", "token-1")
    reload.assert_called_once_with(entry.entry_id)


async def test_the_same_login_again_changes_nothing(hass: HomeAssistant, aioclient_mock) -> None:
    entry, bridge = await _set_up(hass, dict(BEFORE))
    aioclient_mock.get(f"{BEFORE[CONF_API_BASE_URL]}/bridge/connection", json={"mqtt": {**SAME_PLACE_NEW_PASSWORD["mqtt"], "password": "old"}})
    with patch.object(hass.config_entries, "async_schedule_reload", MagicMock()) as reload:
        await bridge.connection_refused_callback()
    assert entry.data["password"] == "old"
    reload.assert_not_called()


async def test_a_bridge_turzi_no_longer_knows_is_shown_as_unlinked(hass: HomeAssistant, aioclient_mock) -> None:
    entry, bridge = await _set_up(hass, dict(BEFORE))
    aioclient_mock.get(f"{BEFORE[CONF_API_BASE_URL]}/bridge/connection", status=401, json={"error": "token_revoked"})
    with patch.object(bridge, "async_stop", AsyncMock()):
        await bridge.connection_refused_callback()
        await hass.async_block_till_done()
    assert dict(entry.data) == BEFORE
    assert any(flow["context"].get("source") == "reauth" for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN))


async def test_the_loop_asks_once_however_often_it_is_refused(hass: HomeAssistant) -> None:
    entry = bridge_entry(hass, domain_filter("lock"), data=dict(BEFORE))
    bridge = TurziMqttBridge.from_config_entry(hass, entry)
    asked = AsyncMock()
    bridge.connection_refused_callback = asked
    refusals = 0

    class Refused:
        def __init__(self, **_kwargs) -> None: ...
        async def __aenter__(self):
            raise MqttConnectError(ReasonCode(PacketTypes.CONNACK, identifier=135))
        async def __aexit__(self, *_exc) -> None: ...

    async def no_wait(delay) -> None:
        # Only the reconnect waits: Home Assistant's own task handling sleeps for zero.
        if not delay:
            return
        nonlocal refusals
        refusals += 1
        if refusals == 4:
            bridge._stopping = True

    with patch("custom_components.turzi_bridge.mqtt_bridge.aiomqtt.Client", Refused), \
         patch("custom_components.turzi_bridge.mqtt_bridge.asyncio.sleep", no_wait):
        await bridge._connection_loop()
        await hass.async_block_till_done()
    assert refusals == 4 and asked.await_count == 1


# --- A Stack that moved to TLS, found again by its certificate (#1005) --------------------------------------------

import aiohttp


def test_only_a_broker_nobody_answers_at_counts_as_unreachable() -> None:
    assert _unreachable(aiomqtt.MqttError("[Errno 111] Connection refused"))
    assert _unreachable(aiomqtt.MqttError("timed out"))
    # A broker that answered is not unreachable: its CONNACK says why.
    assert not _unreachable(MqttConnectError(ReasonCode(PacketTypes.CONNACK, identifier=135)))
    assert not _unreachable(aiomqtt.MqttCodeError(5, "Could not subscribe"))


def _refused_at(aioclient_mock, url: str) -> None:
    aioclient_mock.get(url, exc=aiohttp.ClientConnectorError(MagicMock(), OSError(111, "Connection refused")))


async def test_a_stack_that_moved_to_tls_is_asked_by_the_name_on_its_certificate(hass: HomeAssistant, aioclient_mock) -> None:
    entry, bridge = await _set_up(hass, dict(BEFORE))
    _refused_at(aioclient_mock, f"{BEFORE[CONF_API_BASE_URL]}/bridge/connection")
    aioclient_mock.get(f"{BY_ADDRESS}/bridge/connection", json=NOW)
    with patch("custom_components.turzi_bridge.tls.async_stack_name_at", AsyncMock(return_value=NAME)) as named, \
         patch.object(hass.config_entries, "async_schedule_reload", MagicMock()) as reload:
        await bridge.connection_refused_callback()
    # The address it already had, and nothing else, is where the name was read.
    named.assert_awaited_once_with(hass, ADDRESS, 8126)
    (_m1, first, _d1, _h1), (_m2, second, _d2, headers) = aioclient_mock.mock_calls
    assert str(first) == f"{BEFORE[CONF_API_BASE_URL]}/bridge/connection"
    assert str(second) == f"{BY_ADDRESS}/bridge/connection" and headers["Authorization"] == "Bearer token-1"
    data = entry.data
    assert (data[CONF_BROKER], data[CONF_PORT], data[CONF_USE_TLS], data[CONF_TLS_SERVER_NAME]) == (ADDRESS, 8883, True, NAME)
    assert (data[CONF_API_BASE_URL], data[CONF_API_ADDRESS], data["password"]) == (BY_NAME, ADDRESS, "new")
    assert (data[CONF_HOUSE_ID], data[CONF_BRIDGE_TOKEN]) == ("house-1", "token-1")
    reload.assert_called_once_with(entry.entry_id)


async def test_a_certificate_that_is_not_a_stacks_changes_nothing(hass: HomeAssistant, aioclient_mock) -> None:
    entry, bridge = await _set_up(hass, dict(BEFORE))
    _refused_at(aioclient_mock, f"{BEFORE[CONF_API_BASE_URL]}/bridge/connection")
    with patch("custom_components.turzi_bridge.tls.async_stack_name_at", AsyncMock(return_value=None)), \
         patch.object(hass.config_entries, "async_schedule_reload", MagicMock()) as reload:
        await bridge.connection_refused_callback()
    assert len(aioclient_mock.mock_calls) == 1 and dict(entry.data) == BEFORE
    reload.assert_not_called()


async def test_a_bridge_on_the_cloud_never_reads_a_certificate(hass: HomeAssistant, aioclient_mock) -> None:
    cloud = {**BEFORE, CONF_API_BASE_URL: "https://api.turzi.com/api/v2"}
    entry, bridge = await _set_up(hass, cloud)
    _refused_at(aioclient_mock, "https://api.turzi.com/api/v2/bridge/connection")
    with patch("custom_components.turzi_bridge.tls.async_stack_name_at", AsyncMock()) as named:
        await bridge.connection_refused_callback()
    named.assert_not_awaited()
    assert dict(entry.data) == cloud


async def test_the_loop_asks_once_when_nobody_answers(hass: HomeAssistant) -> None:
    entry = bridge_entry(hass, domain_filter("lock"), data=dict(BEFORE))
    bridge = TurziMqttBridge.from_config_entry(hass, entry)
    asked = AsyncMock()
    bridge.connection_refused_callback = asked
    attempts = 0

    class Nobody:
        def __init__(self, **_kwargs) -> None: ...
        async def __aenter__(self):
            raise aiomqtt.MqttError("[Errno 111] Connection refused")
        async def __aexit__(self, *_exc) -> None: ...

    async def no_wait(delay) -> None:
        if not delay:
            return
        nonlocal attempts
        attempts += 1
        if attempts == 3:
            bridge._stopping = True

    with patch("custom_components.turzi_bridge.mqtt_bridge.aiomqtt.Client", Nobody), \
         patch("custom_components.turzi_bridge.mqtt_bridge.asyncio.sleep", no_wait):
        await bridge._connection_loop()
        await hass.async_block_till_done()
    assert attempts == 3 and asked.await_count == 1
