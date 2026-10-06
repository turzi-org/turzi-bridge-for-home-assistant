"""Publishing and cleanup apply the same rule as the catalog."""

import json

from homeassistant.core import HomeAssistant

from custom_components.turzi_bridge.const import DEFAULT_INCLUDED_BINARY_SENSOR_CLASSES
from custom_components.turzi_bridge.mqtt_bridge import TurziMqttBridge

from .helpers import HOUSE, FakeClient

DOOR = "binary_sensor.puerta_principal"
MOTION = "binary_sensor.movimiento_hall"


def make_bridge(hass: HomeAssistant, **over) -> TurziMqttBridge:
    params = dict(
        hass=hass, broker="localhost", port=1883, username=None, password=None,
        house_id=HOUSE, use_tls=False, entry_id="entry-1",
        exposed_entities=[], included_domains=["light"], auto_add_new=True,
        never_expose=[], included_binary_sensor_classes=list(DEFAULT_INCLUDED_BINARY_SENSOR_CLASSES),
    )
    params.update(over)
    return TurziMqttBridge(**params)


async def test_should_expose_reads_the_class_from_the_state(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass)
    hass.states.async_set(DOOR, "off", {"device_class": "door"})
    hass.states.async_set(MOTION, "on", {"device_class": "motion"})

    assert bridge.should_expose(DOOR)
    assert not bridge.should_expose(MOTION)
    assert not bridge.should_expose("binary_sensor.not_there_yet")


async def test_the_blocklist_wins_over_a_class(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass, never_expose=[DOOR])
    hass.states.async_set(DOOR, "off", {"device_class": "door"})

    assert not bridge.should_expose(DOOR)


async def test_a_door_opening_is_published(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass)
    client = FakeClient()
    bridge._client = client
    bridge._setup_state_listener()

    hass.states.async_set(DOOR, "on", {"device_class": "door"})
    await hass.async_block_till_done()

    assert client.published(DOOR)
    payload = json.loads(next(p for t, p, _ in client.publishes if t.endswith("/binary_sensor/puerta_principal")))
    assert payload["state"] == "on"
    assert payload["attributes"] == {"device_class": "door"}


async def test_a_sensor_reclassed_out_of_the_list_is_cleared_from_the_broker(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass)
    client = FakeClient()
    bridge._client = client
    hass.states.async_set(DOOR, "off", {"device_class": "door"})
    bridge._published_entities.add(DOOR)
    bridge._setup_state_listener()

    hass.states.async_set(DOOR, "off", {"device_class": "motion"})
    await hass.async_block_till_done()

    assert client.cleared(DOOR)
    assert DOOR not in bridge._published_entities


async def test_removing_a_class_clears_its_sensors_and_adding_it_publishes_them(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass)
    client = FakeClient()
    bridge._client = client
    hass.states.async_set(DOOR, "off", {"device_class": "door"})
    bridge._published_entities.add(DOOR)

    bridge.update_config(
        exposed_entities=[], included_domains=["light"], auto_add_new=True, never_expose=[],
        included_binary_sensor_classes=["smoke"],
    )
    await hass.async_block_till_done()
    assert client.cleared(DOOR)

    bridge.update_config(
        exposed_entities=[], included_domains=["light"], auto_add_new=True, never_expose=[],
        included_binary_sensor_classes=["door"],
    )
    await hass.async_block_till_done()
    assert client.published(DOOR)


async def test_reconnecting_clears_what_left_the_scope_and_keeps_the_doors(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass)
    client = FakeClient()
    hass.states.async_set(DOOR, "off", {"device_class": "door"})
    hass.states.async_set(MOTION, "on", {"device_class": "motion"})
    bridge._published_entities.update({DOOR, MOTION})

    await bridge._reconcile_retained_state(client)

    assert client.cleared(MOTION)
    assert not client.cleared(DOOR)
