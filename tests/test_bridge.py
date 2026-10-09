"""Publishing and cleanup apply the rows, and change the moment a row does."""

import json

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant

from custom_components.turzi_bridge.exposure import PublishScope
from custom_components.turzi_bridge.mqtt_bridge import TurziMqttBridge

from .helpers import HOUSE, FakeClient, bridge_entry, domain_filter, door_and_safety, exclusion

DOOR = "binary_sensor.puerta_principal"
MOTION = "binary_sensor.movimiento_hall"


def make_bridge(hass: HomeAssistant, entry) -> TurziMqttBridge:
    bridge = TurziMqttBridge.from_config_entry(hass, entry)
    bridge._client = FakeClient()
    return bridge


def test_from_config_entry_reads_rows_and_exclusions(hass: HomeAssistant) -> None:
    entry = bridge_entry(hass, door_and_safety(), domain_filter("light"), exclusion("light.dormitorio"))
    hass.states.async_set(DOOR, "off", {"device_class": "door"})
    hass.states.async_set(MOTION, "on", {"device_class": "motion"})
    hass.states.async_set("light.hall", "on", {})
    hass.states.async_set("light.dormitorio", "on", {})

    bridge = TurziMqttBridge.from_config_entry(hass, entry)

    assert bridge.should_expose(DOOR)
    assert bridge.should_expose("light.hall")
    assert not bridge.should_expose(MOTION)
    assert not bridge.should_expose("light.dormitorio")
    assert not bridge.should_expose("binary_sensor.not_there_yet")


async def test_a_door_opening_is_published(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass, bridge_entry(hass, door_and_safety()))
    bridge._setup_state_listener()

    hass.states.async_set(DOOR, "on", {"device_class": "door"})
    await hass.async_block_till_done()

    topic = f"house/{HOUSE}/state/binary_sensor/puerta_principal"
    payload = json.loads(next(p for t, p, _ in bridge._client.publishes if t == topic))
    assert payload["state"] == "on" and payload["attributes"] == {"device_class": "door"}


async def test_a_sensor_reclassed_out_of_its_filter_is_cleared(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass, bridge_entry(hass, door_and_safety()))
    hass.states.async_set(DOOR, "off", {"device_class": "door"})
    bridge._published_entities.add(DOOR)
    bridge._setup_state_listener()

    hass.states.async_set(DOOR, "off", {"device_class": "motion"})
    await hass.async_block_till_done()

    assert bridge._client.cleared(DOOR)
    assert DOOR not in bridge._published_entities


async def test_deleting_and_adding_a_row_clears_and_publishes_through_the_update_listener(
    hass: HomeAssistant,
) -> None:
    from custom_components.turzi_bridge import _async_options_updated
    from custom_components.turzi_bridge.const import DOMAIN

    entry = bridge_entry(hass, domain_filter("light"))
    bridge = make_bridge(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"bridge": bridge, "cloud": None}
    entry.add_update_listener(_async_options_updated)
    hass.states.async_set("light.hall", "on", {})
    bridge._published_entities.add("light.hall")

    light_row = next(iter(entry.subentries))
    hass.config_entries.async_remove_subentry(entry, light_row)
    await hass.async_block_till_done()
    assert bridge._client.cleared("light.hall")

    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(data={"domain": "light", "device_classes": []}, subentry_type="domain_filter", title="Light", unique_id="light"),
    )
    await hass.async_block_till_done()
    assert bridge._client.published("light.hall")


async def test_an_exclusion_added_later_clears_what_it_names(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass, bridge_entry(hass, domain_filter("light")))
    hass.states.async_set("light.dormitorio", "on", {})
    bridge._published_entities.add("light.dormitorio")

    bridge.update_config(scope=PublishScope.from_filters([{"domain": "light"}]), never_expose=["light.dormitorio"])
    await hass.async_block_till_done()

    assert bridge._client.cleared("light.dormitorio")


async def test_reconnecting_clears_what_left_the_scope_and_keeps_the_rest(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass, bridge_entry(hass, door_and_safety()))
    hass.states.async_set(DOOR, "off", {"device_class": "door"})
    hass.states.async_set(MOTION, "on", {"device_class": "motion"})
    bridge._published_entities.update({DOOR, MOTION})

    await bridge._reconcile_retained_state(bridge._client)

    assert bridge._client.cleared(MOTION)
    assert not bridge._client.cleared(DOOR)


async def test_a_cover_publishes_which_services_it_accepts(hass: HomeAssistant) -> None:
    """supported_features is published unchanged (Turzi Protocol v1.1 §4).

    Dev Smoke Test's garage published only its position, so the app offered a
    position slider that HA refused on every drag.
    """
    garage = "cover.garage1"
    bridge = make_bridge(hass, bridge_entry(hass, domain_filter("cover")))
    bridge._setup_state_listener()

    # OPEN | CLOSE | STOP: a garage door, no SET_POSITION.
    hass.states.async_set(garage, "closed", {"device_class": "garage", "current_position": 0, "supported_features": 11})
    await hass.async_block_till_done()

    payload = json.loads(next(p for t, p, _ in bridge._client.publishes if t == f"house/{HOUSE}/state/cover/garage1"))
    assert payload["attributes"] == {"device_class": "garage", "current_position": 0, "supported_features": 11}


async def test_a_domain_without_an_attribute_map_still_publishes_its_features(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass, bridge_entry(hass, domain_filter("lock")))
    bridge._setup_state_listener()

    hass.states.async_set("lock.porton", "locked", {"supported_features": 1})
    await hass.async_block_till_done()

    payload = json.loads(next(p for t, p, _ in bridge._client.publishes if t == f"house/{HOUSE}/state/lock/porton"))
    assert payload["attributes"] == {"supported_features": 1}
