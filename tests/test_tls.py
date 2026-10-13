"""A Turzi Stack in the building: reached by its address, verified for its name (tls.py)."""

from __future__ import annotations

import ssl
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.core import HomeAssistant

from custom_components.turzi_bridge import tls
from custom_components.turzi_bridge.const import (
    CONF_API_ADDRESS,
    CONF_API_BASE_URL,
    CONF_BROKER,
    CONF_ENROLLMENT_TOKEN,
    CONF_TLS_SERVER_NAME,
    CONF_USE_TLS,
    DOMAIN,
)
from custom_components.turzi_bridge.enrollment import EnrollResult, async_enroll

NAME = "k7q2m9xw3d.stack.turzi.cloud"
ADDRESS = "10.0.0.5"
BY_NAME = f"https://{NAME}:8126/api/v2"
BY_ADDRESS = f"https://{ADDRESS}:8126/api/v2"


def test_the_address_is_dialled_first_and_the_name_is_what_is_verified() -> None:
    assert tls.ways(BY_NAME, ADDRESS) == [(BY_ADDRESS, NAME), (BY_NAME, None)]


@pytest.mark.parametrize(
    ("base_url", "address"),
    [
        ("https://api.turzi.com/api/v2", None),              # the cloud, as always
        ("https://api.turzi.com/api/v2", ""),
        (f"http://{ADDRESS}:8126/api/v2", ADDRESS),          # a Stack with no certificate: nothing to verify
        (BY_ADDRESS, ADDRESS),                               # already an address: no name to verify it for
    ],
)
def test_anything_else_is_called_as_its_url_says(base_url: str, address: str | None) -> None:
    assert tls.ways(base_url, address) == [(base_url, None)]


def test_the_context_checks_one_name_whatever_is_dialled() -> None:
    context = tls.stack_context(NAME)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert context.verify_flags & ssl.VERIFY_X509_STRICT
    asked: list[str | None] = []
    with patch.object(ssl.SSLContext, "wrap_bio", lambda _self, _i, _o, *a, server_hostname=None, **k: asked.append(server_hostname)):
        context.wrap_bio(ssl.MemoryBIO(), ssl.MemoryBIO(), server_hostname=ADDRESS)
    assert asked == [NAME]


SERVER_BODY = {
    "house_id": "house-1",
    "bridge_token": "token-1",
    "mqtt": {"host": ADDRESS, "port": 8883, "tls": True, "tls_server_name": NAME, "username": "bridge-house-1", "password": "secret"},
    "api": {"base_url": BY_NAME, "address": ADDRESS},
}


async def test_enrolling_through_a_stack_dials_its_address(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.post(f"{BY_ADDRESS}/bridge/enroll", json=SERVER_BODY)
    result = await async_enroll(hass, BY_NAME, "TRZ-AAAA-BBBB-CCCC", ADDRESS)
    assert (result.mqtt_host, result.mqtt_port, result.mqtt_tls, result.mqtt_tls_server_name) == (ADDRESS, 8883, True, NAME)
    assert (result.api_base_url, result.api_address) == (BY_NAME, ADDRESS)
    (_method, url, _data, _headers), = aioclient_mock.mock_calls
    assert str(url) == f"{BY_ADDRESS}/bridge/enroll"


async def test_a_stack_that_moved_is_found_by_its_name(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.post(f"{BY_ADDRESS}/bridge/enroll", exc=aiohttp.ClientConnectorError(None, OSError("nobody there")))
    aioclient_mock.post(f"{BY_NAME}/bridge/enroll", json=SERVER_BODY)
    result = await async_enroll(hass, BY_NAME, "TRZ-AAAA-BBBB-CCCC", ADDRESS)
    assert result.house_id == "house-1"
    assert [str(call[1]) for call in aioclient_mock.mock_calls] == [f"{BY_ADDRESS}/bridge/enroll", f"{BY_NAME}/bridge/enroll"]


async def test_the_cloud_answers_without_a_stack_as_before(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.post("https://api.turzi.com/api/v2/bridge/enroll", json={
        "house_id": "house-1", "bridge_token": "token-1",
        "mqtt": {"host": "broker.example", "port": 1883, "tls": False, "username": "u", "password": "p"}})
    result = await async_enroll(hass, "https://api.turzi.com/api/v2", "TRZ-AAAA-BBBB-CCCC")
    assert (result.mqtt_tls_server_name, result.api_base_url, result.api_address) == (None, None, None)


async def test_what_the_stack_gave_and_what_the_api_answered_are_kept(hass: HomeAssistant) -> None:
    enrolled = EnrollResult(
        house_id="house-1", bridge_token="token-1", mqtt_host=ADDRESS, mqtt_port=8883, mqtt_tls=True,
        mqtt_username="bridge-house-1", mqtt_password="secret", mqtt_tls_server_name=NAME, api_base_url=BY_NAME, api_address=ADDRESS)
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    flow = await hass.config_entries.flow.async_configure(flow["flow_id"], {"next_step_id": "cloud"})
    with patch("custom_components.turzi_bridge.config_flow.async_enroll", return_value=enrolled) as asked:
        flow = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {CONF_ENROLLMENT_TOKEN: "TRZ-AAAA-BBBB-CCCC", CONF_API_BASE_URL: BY_NAME, CONF_API_ADDRESS: ADDRESS})
    assert asked.call_args.args[1:] == (BY_NAME, "TRZ-AAAA-BBBB-CCCC", ADDRESS)
    with patch("custom_components.turzi_bridge.async_setup_entry", return_value=True):
        done = await hass.config_entries.flow.async_configure(flow["flow_id"], {"auto_add_new": True})
    data = done["data"]
    assert (data[CONF_BROKER], data[CONF_USE_TLS], data[CONF_TLS_SERVER_NAME]) == (ADDRESS, True, NAME)
    assert (data[CONF_API_BASE_URL], data[CONF_API_ADDRESS]) == (BY_NAME, ADDRESS)
