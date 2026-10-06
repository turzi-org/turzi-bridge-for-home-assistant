"""The bridge page's three add buttons, and editing a row."""

import voluptuous as vol
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.turzi_bridge.const import CONF_FILTER_SNAPSHOT

from .helpers import bridge_entry, domain_filter, door_and_safety, entity_filter


async def _add(hass, entry, kind):
    return await hass.config_entries.subentries.async_init((entry.entry_id, kind), context={"source": SOURCE_USER})


def _row(entry, kind):
    return [s for s in entry.subentries.values() if s.subentry_type == kind]


async def test_a_domain_with_classes_asks_for_them_and_none_ticked_is_the_whole_domain(hass: HomeAssistant) -> None:
    entry = bridge_entry(hass, domain_filter("light"))
    result = await _add(hass, entry, "domain_filter")
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
    domains = {o["value"] for o in result["data_schema"].schema["domain"].config["options"]}
    assert {"sensor", "binary_sensor", "scene"} <= domains

    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"domain": "sensor"})
    assert result["step_id"] == "classes"
    classes = {o["value"] for o in result["data_schema"].schema["device_classes"].config["options"]}
    assert {"temperature", "humidity", "power"} <= classes and "door" not in classes

    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"device_classes": []})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    sensor = next(s for s in _row(entry, "domain_filter") if s.unique_id == "sensor")
    assert dict(sensor.data) == {"domain": "sensor", "device_classes": []}
    assert sensor.title == "Sensor"


async def test_ticked_classes_go_in_the_filter_and_its_title(hass: HomeAssistant) -> None:
    entry = bridge_entry(hass)
    result = await _add(hass, entry, "domain_filter")
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"domain": "binary_sensor"})
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"device_classes": ["door", "window"]})

    row = _row(entry, "domain_filter")[0]
    assert dict(row.data) == {"domain": "binary_sensor", "device_classes": ["door", "window"]}
    assert row.title == "Binary sensor: Door, Window"


async def test_a_domain_without_classes_skips_that_step(hass: HomeAssistant) -> None:
    entry = bridge_entry(hass)
    result = await _add(hass, entry, "domain_filter")

    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"domain": "scene"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert dict(_row(entry, "domain_filter")[0].data) == {"domain": "scene", "device_classes": []}


async def test_the_domain_starts_empty_and_is_asked_for(hass: HomeAssistant) -> None:
    # Home Assistant fills a required list with its first option: one Submit
    # would have added whatever domain sorts first.
    entry = bridge_entry(hass)
    result = await _add(hass, entry, "domain_filter")
    field = next(k for k in result["data_schema"].schema if k == "domain")
    assert not isinstance(field, vol.Required)

    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {})

    assert result["errors"] == {"domain": "domain_required"}
    assert not entry.subentries


async def test_a_domain_that_already_has_a_row_is_refused(hass: HomeAssistant) -> None:
    entry = bridge_entry(hass, domain_filter("light"))
    result = await _add(hass, entry, "domain_filter")

    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"domain": "light"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"domain": "domain_filter_exists"}


async def test_editing_a_row_keeps_its_ticks_and_saves_in_place(hass: HomeAssistant) -> None:
    entry = bridge_entry(hass, door_and_safety())
    row = _row(entry, "domain_filter")[0]
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "domain_filter"), context={"source": SOURCE_RECONFIGURE, "subentry_id": row.subentry_id}
    )
    assert result["data_schema"].schema["domain"].config["options"]
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"domain": "binary_sensor"})
    ticked = next(k for k in result["data_schema"].schema if k == "device_classes").default()
    assert set(ticked) == set(row.data["device_classes"])

    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"device_classes": ["door"]})

    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    assert dict(entry.subentries[row.subentry_id].data) == {"domain": "binary_sensor", "device_classes": ["door"]}


async def test_an_entity_filter_is_searched_and_titled_by_its_entities(hass: HomeAssistant) -> None:
    hass.states.async_set("switch.bomba", "off", {"friendly_name": "Bomba de agua"})
    hass.states.async_set("input_boolean.calefon", "off", {"friendly_name": "Calefón"})
    entry = bridge_entry(hass)
    result = await _add(hass, entry, "entity_filter")
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"entities": []})
    assert result["errors"] == {"entities": "no_entities"}

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"entities": ["switch.bomba", "input_boolean.calefon"]}
    )

    row = _row(entry, "entity_filter")[0]
    assert dict(row.data) == {"entities": ["switch.bomba", "input_boolean.calefon"]}
    assert row.title == "Bomba de agua, Calefón"


async def test_an_exclusion_is_its_own_kind_of_row(hass: HomeAssistant) -> None:
    hass.states.async_set("light.dormitorio", "on", {"friendly_name": "Luz Dormitorio"})
    entry = bridge_entry(hass, domain_filter("light"))
    result = await _add(hass, entry, "exclusion")

    await hass.config_entries.subentries.async_configure(result["flow_id"], {"entities": ["light.dormitorio"]})

    assert [dict(s.data) for s in _row(entry, "exclusion")] == [{"entities": ["light.dormitorio"]}]
    assert _row(entry, "exclusion")[0].title == "Luz Dormitorio"


async def test_with_automatic_exposure_off_a_new_domain_filter_takes_what_exists_now(hass: HomeAssistant) -> None:
    hass.states.async_set("scene.noche", "scening", {})
    entry = bridge_entry(hass, entity_filter("switch.bomba"), options={"auto_add_new": False, CONF_FILTER_SNAPSHOT: []})
    result = await _add(hass, entry, "domain_filter")

    await hass.config_entries.subentries.async_configure(result["flow_id"], {"domain": "scene"})

    assert entry.options[CONF_FILTER_SNAPSHOT] == ["scene.noche"]
