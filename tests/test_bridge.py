"""Publishing and cleanup apply the rows, and change the moment a row does."""

import json
from pathlib import Path

from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
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


async def test_a_fan_says_its_speeds_and_presets(hass: HomeAssistant) -> None:
    """The app's numbered-speed tile and presets need them (app APP_WORK §19)."""
    bridge = make_bridge(hass, bridge_entry(hass, domain_filter("fan")))
    bridge._setup_state_listener()
    hass.states.async_set("fan.techo", "on", {"percentage": 50, "percentage_step": 33.333333333333336, "preset_modes": ["auto", "sleep"], "preset_mode": None})
    await hass.async_block_till_done()
    payload = json.loads(next(p for t, p, _ in bridge._client.publishes if t == f"house/{HOUSE}/state/fan/techo"))
    assert payload["attributes"]["percentage_step"] == 33.333333333333336
    assert payload["attributes"]["preset_modes"] == ["auto", "sleep"]


async def test_a_sensor_says_its_state_class(hass: HomeAssistant) -> None:
    """A meter is summed and a reading averaged only if the platform is told which is which (turzi-apps D59)."""
    bridge = make_bridge(hass, bridge_entry(hass, domain_filter("sensor")))
    bridge._setup_state_listener()

    hass.states.async_set("sensor.agua", "1234.5", {"unit_of_measurement": "m³", "device_class": "water", "state_class": "total_increasing"})
    hass.states.async_set("sensor.temp", "21.5", {"unit_of_measurement": "°C", "device_class": "temperature"})
    await hass.async_block_till_done()

    def attributes(object_id: str) -> dict:
        return json.loads(next(p for t, p, _ in bridge._client.publishes if t == f"house/{HOUSE}/state/sensor/{object_id}"))["attributes"]

    assert attributes("agua") == {"unit_of_measurement": "m³", "device_class": "water", "state_class": "total_increasing"}
    assert attributes("temp") == {"unit_of_measurement": "°C", "device_class": "temperature"}


async def test_an_event_entity_leaves_only_as_a_turzi_event(hass: HomeAssistant) -> None:
    """A door said that it opened and how, never by whom (turzi-apps D56, STACK_AUTOMATIONS.md §8a.4)."""
    bridge = make_bridge(hass, bridge_entry(hass, domain_filter("event")))
    bridge._setup_state_listener()

    hass.states.async_set("event.puerta_akuvox", "2026-10-19T12:00:00+00:00", {
        "event_type": "valid_card", "event_types": ["valid_card", "invalid_card"],
        "username": "Olga Pérez", "user_id": "user-1234", "card_no": "A1B2C3D4",
    })
    hass.states.async_set("event.timbre", "2026-10-19T12:00:01+00:00", {"event_type": "ring", "device_class": "doorbell"})
    hass.states.async_set("event.hik", "2026-10-19T12:00:02+00:00", {"event_type": "door_open_abnormal", "employee_no": "emp-77", "name": "x"})
    hass.states.async_set("event.otra_cosa", "2026-10-19T12:00:03+00:00", {"event_type": "tamper", "name": "Olga"})
    await hass.async_block_till_done()

    published = {t: json.loads(p) for t, p, _ in bridge._client.publishes if t.startswith(f"house/{HOUSE}/state/event/")}
    door = published[f"house/{HOUSE}/state/event/puerta_akuvox"]
    assert door["attributes"] == {"event_type": "access_granted", "event_types": ["ring", "access_granted", "access_denied", "door_forced"], "method": "tag"}
    assert door["state"] == "2026-10-19T12:00:00+00:00"
    assert published[f"house/{HOUSE}/state/event/timbre"]["attributes"]["event_type"] == "ring"
    assert published[f"house/{HOUSE}/state/event/hik"]["attributes"]["event_type"] == "door_forced"
    assert f"house/{HOUSE}/state/event/otra_cosa" not in published
    everything = json.dumps(list(published.values()))
    # Values no timestamp can hold: a bare "77" or "1234" turns up in last_changed's microseconds now and then (#1161).
    for identity in ("Olga", "user-1234", "A1B2C3D4", "employee_no", "emp-77"):
        assert identity not in everything


async def test_it_says_which_version_it_is_when_it_announces_itself(hass: HomeAssistant) -> None:
    """What replaces a bridge knows the new one connected by the version it says (turzi-apps TURZI_SUPERVISOR.md §6.2)."""
    bridge = make_bridge(hass, bridge_entry(hass, door_and_safety()))
    await bridge._async_read_version()
    await bridge._publish_availability(bridge._client, "online")
    await bridge._publish_availability(bridge._client, "offline", "connection_lost")

    manifest = json.loads((Path(__file__).parents[1] / "custom_components/turzi_bridge/manifest.json").read_text())
    said = [json.loads(p) for t, p, _ in bridge._client.publishes if t == f"house/{HOUSE}/availability"]
    assert said[0]["state"] == "online" and said[0]["bridge_version"] == manifest["version"]
    assert said[1]["state"] == "offline" and "bridge_version" not in said[1]
    assert all(retain for t, _, retain in bridge._client.publishes if t == f"house/{HOUSE}/availability")


async def test_it_says_it_is_leaving_when_home_assistant_stops(hass: HomeAssistant) -> None:
    """Home Assistant stopping does not unload the bridge: without this, "online" stayed on the broker all through a restart."""
    bridge = make_bridge(hass, bridge_entry(hass, door_and_safety()))
    bridge._setup_stop_listener()

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    assert (f"house/{HOUSE}/availability", json.dumps({"state": "offline", "reason": "shutdown"}), True) in bridge._client.publishes
    assert bridge._unsub_stop_listener is None


async def test_unloading_says_it_once_and_stops_listening_for_the_stop(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass, bridge_entry(hass, door_and_safety()))
    bridge._setup_stop_listener()

    await bridge.async_stop()
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    goodbyes = [p for t, p, _ in bridge._client.publishes if t == f"house/{HOUSE}/availability"]
    assert goodbyes == [json.dumps({"state": "offline", "reason": "shutdown"})]

