"""The publish-scope rule on its own (`exposure.in_publish_scope`)."""

from custom_components.turzi_bridge.const import DEFAULT_INCLUDED_BINARY_SENSOR_CLASSES
from custom_components.turzi_bridge.exposure import in_publish_scope


def scope(entity_id, device_class=None, *, domains=(), exposed=(), classes=DEFAULT_INCLUDED_BINARY_SENSOR_CLASSES):
    return in_publish_scope(
        entity_id,
        device_class,
        included_domains=set(domains),
        exposed_entities=set(exposed),
        binary_sensor_classes=set(classes),
    )


def test_a_door_contact_is_included_by_its_class():
    assert scope("binary_sensor.puerta_principal", "door")


def test_every_default_class_is_door_or_life_safety():
    assert set(DEFAULT_INCLUDED_BINARY_SENSOR_CLASSES) == {
        "door", "garage_door", "opening", "window", "smoke", "gas", "carbon_monoxide", "moisture",
    }


def test_motion_occupancy_and_unclassified_sensors_stay_out():
    assert not scope("binary_sensor.hall", "motion")
    assert not scope("binary_sensor.living", "occupancy")
    assert not scope("binary_sensor.unknown", None)


def test_the_class_rule_is_for_binary_sensors_only():
    # `sensor` has a `moisture` class of its own (a reading, not a leak alarm).
    assert not scope("sensor.humedad_living", "moisture")


def test_an_empty_class_list_includes_no_binary_sensor():
    assert not scope("binary_sensor.puerta_principal", "door", classes=())


def test_a_whole_domain_and_a_manual_addition_still_count():
    assert scope("binary_sensor.hall", "motion", domains={"binary_sensor"})
    assert scope("binary_sensor.hall", "motion", exposed={"binary_sensor.hall"})
    assert scope("light.hall", None, domains={"light"})
    assert not scope("light.hall", None)
