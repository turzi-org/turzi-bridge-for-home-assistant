"""The publish-scope rule on its own (`exposure.PublishScope`)."""

from custom_components.turzi_bridge.const import DEFAULT_FILTERS, DOOR_AND_SAFETY_CLASSES
from custom_components.turzi_bridge.exposure import PublishScope

DOOR_FILTER = {"domain": "binary_sensor", "device_classes": list(DOOR_AND_SAFETY_CLASSES)}


def test_a_domain_filter_without_classes_takes_the_whole_domain():
    scope = PublishScope.from_filters([{"domain": "light", "device_classes": []}])

    assert scope.includes("light.hall", None)
    assert not scope.includes("switch.hall", None)


def test_a_class_filter_takes_only_its_classes():
    scope = PublishScope.from_filters([DOOR_FILTER])

    assert scope.includes("binary_sensor.puerta", "door")
    assert scope.includes("binary_sensor.humo", "smoke")
    assert not scope.includes("binary_sensor.hall", "motion")
    assert not scope.includes("binary_sensor.sin_clase", None)


def test_classes_belong_to_their_domain():
    # `sensor` has a `moisture` class of its own (a reading, not a leak alarm).
    assert not PublishScope.from_filters([DOOR_FILTER]).includes("sensor.humedad", "moisture")


def test_an_entity_filter_takes_its_entities_of_any_domain():
    scope = PublishScope.from_filters([{"entities": ["switch.bomba", "input_boolean.calefon"]}])

    assert scope.includes("switch.bomba", None)
    assert scope.includes("input_boolean.calefon", None)
    assert not scope.includes("switch.otra", None)


def test_a_whole_domain_wins_over_a_class_filter_on_it():
    scope = PublishScope.from_filters([DOOR_FILTER, {"domain": "binary_sensor", "device_classes": []}])

    assert scope.includes("binary_sensor.hall", "motion")
    assert not scope.needs_device_class("binary_sensor.hall")


def test_with_automatic_exposure_off_domain_filters_keep_to_the_snapshot():
    scope = PublishScope.from_filters(
        [{"domain": "light", "device_classes": []}, {"entities": ["switch.bomba"]}],
        auto_add_new=False,
        snapshot=["light.hall"],
    )

    assert scope.includes("light.hall", None)
    assert not scope.includes("light.nueva", None)
    # Entity filters name their entities: the snapshot does not apply to them.
    assert scope.includes("switch.bomba", None)


def test_the_defaults_are_eight_domains_and_the_door_and_safety_classes():
    assert [f["domain"] for f in DEFAULT_FILTERS] == [
        "alarm_control_panel", "climate", "cover", "fan", "light", "lock", "siren", "switch", "binary_sensor",
    ]
    assert DEFAULT_FILTERS[-1]["device_classes"] == list(DOOR_AND_SAFETY_CLASSES)
    assert set(DOOR_AND_SAFETY_CLASSES) == {
        "door", "garage_door", "opening", "window", "smoke", "gas", "carbon_monoxide", "moisture",
    }
    scope = PublishScope.from_filters(DEFAULT_FILTERS)
    assert not scope.includes("input_boolean.calefon", None)
    assert not scope.includes("script.riego", None)
