"""Every class in the picker has a label, in every language, and HA's list is ours."""

import json
from pathlib import Path

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.turzi_bridge.const import (
    DEFAULT_INCLUDED_BINARY_SENSOR_CLASSES,
    SELECTABLE_BINARY_SENSOR_CLASSES,
)

ROOT = Path(__file__).parent.parent / "custom_components" / "turzi_bridge"
FILES = [ROOT / "strings.json", ROOT / "translations" / "en.json", ROOT / "translations" / "es.json"]


def test_the_picker_offers_every_class_home_assistant_defines():
    assert set(SELECTABLE_BINARY_SENSOR_CLASSES) == {c.value for c in BinarySensorDeviceClass}
    assert set(DEFAULT_INCLUDED_BINARY_SENSOR_CLASSES) <= set(SELECTABLE_BINARY_SENSOR_CLASSES)


def test_every_class_and_the_field_are_worded_in_every_file():
    for path in FILES:
        strings = json.loads(path.read_text())
        labels = strings["selector"]["binary_sensor_class"]["options"]
        assert set(labels) == set(SELECTABLE_BINARY_SENSOR_CLASSES), path.name
        step = strings["options"]["step"]["init"]
        assert step["data"]["included_binary_sensor_classes"], path.name
        assert step["data_description"]["included_binary_sensor_classes"], path.name
