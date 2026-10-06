"""Setting the bridge up from scratch: connection, «Opciones», then the rows."""

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.turzi_bridge.const import (
    CONF_AUTO_ADD_NEW,
    CONF_FILTER_SNAPSHOT,
    DEFAULT_FILTERS,
    DOMAIN,
)
from custom_components.turzi_bridge.enrollment import EnrollResult

MANUAL = {"broker": "127.0.0.1", "port": 1884, "username": "", "password": "", "house_id": "preview", "use_tls": False}


async def _start(hass: HomeAssistant, mode: str):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": mode})


async def test_manual_setup_ends_in_options_and_creates_the_preloaded_rows(hass: HomeAssistant) -> None:
    hass.states.async_set("light.hall", "on", {})
    hass.states.async_set("binary_sensor.puerta", "off", {"device_class": "door"})
    hass.states.async_set("input_boolean.calefon", "off", {})
    result = await _start(hass, "manual")

    with patch("custom_components.turzi_bridge.config_flow._test_mqtt_connection", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], MANUAL)

    assert result["type"] is FlowResultType.FORM and result["step_id"] == "settings"
    assert result["description_placeholders"] == {"filters": "9", "published": "2"}
    field = next(k for k in result["data_schema"].schema if k == CONF_AUTO_ADD_NEW)
    assert field.default() is True

    with patch("custom_components.turzi_bridge.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_AUTO_ADD_NEW: True})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert (entry.version, entry.minor_version) == (3, 1)
    assert entry.data["mode"] == "manual"
    assert entry.options[CONF_AUTO_ADD_NEW] is True
    assert entry.options[CONF_FILTER_SNAPSHOT] == ["binary_sensor.puerta", "light.hall"]
    rows = [(s.subentry_type, dict(s.data), s.unique_id) for s in entry.subentries.values()]
    assert [(t, d) for t, d, _ in rows] == [("domain_filter", f) for f in DEFAULT_FILTERS]
    assert all(u == d["domain"] for _, d, u in rows)
    titles = {s.unique_id: s.title for s in entry.subentries.values()}
    assert titles["light"] == "Light"
    assert titles["binary_sensor"].startswith("Binary sensor: ")


async def test_cloud_setup_enrolls_then_asks_the_options(hass: HomeAssistant) -> None:
    result = await _start(hass, "cloud")
    enrolled = EnrollResult(
        house_id="937098a0", bridge_token="t", mqtt_host="broker.turzi.cloud", mqtt_port=8883,
        mqtt_username="u", mqtt_password="p", mqtt_tls=True,
    )
    with patch("custom_components.turzi_bridge.config_flow.async_enroll", return_value=enrolled):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"enrollment_key": "TRZ-AAAA-BBBB-CCCC", "api_base_url": "https://api.dev.turzi.com/api/v2"}
        )
    assert result["step_id"] == "settings"

    with patch("custom_components.turzi_bridge.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_AUTO_ADD_NEW: False})

    entry = result["result"]
    assert entry.title == "turzi Bridge for Home Assistant — 937098a0"
    assert entry.data["bridge_token"] == "t" and entry.data["mode"] == "cloud"
    assert entry.options[CONF_AUTO_ADD_NEW] is False
    assert len(entry.subentries) == len(DEFAULT_FILTERS)
