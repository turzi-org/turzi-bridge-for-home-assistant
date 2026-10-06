"""Existing installations get the classes once, and keep their own if set."""

import logging

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.turzi_bridge import async_migrate_entry
from custom_components.turzi_bridge.const import (
    CONF_EXPOSED_ENTITIES,
    CONF_INCLUDED_BINARY_SENSOR_CLASSES,
    CONF_INCLUDED_DOMAINS,
    DEFAULT_INCLUDED_BINARY_SENSOR_CLASSES,
    DOMAIN,
)


def entry(hass: HomeAssistant, *, version: int, minor_version: int, data: dict, options: dict) -> MockConfigEntry:
    e = MockConfigEntry(domain=DOMAIN, version=version, minor_version=minor_version, data=data, options=options)
    e.add_to_hass(hass)
    return e


async def test_a_2_1_entry_gets_the_door_and_safety_classes_and_says_so(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    e = entry(hass, version=2, minor_version=1, data={"mode": "cloud", "house_id": "h1"},
              options={CONF_INCLUDED_DOMAINS: ["light"], CONF_EXPOSED_ENTITIES: []})

    with caplog.at_level(logging.WARNING):
        assert await async_migrate_entry(hass, e)

    assert (e.version, e.minor_version) == (2, 2)
    assert e.options[CONF_INCLUDED_BINARY_SENSOR_CLASSES] == DEFAULT_INCLUDED_BINARY_SENSOR_CLASSES
    assert e.options[CONF_INCLUDED_DOMAINS] == ["light"]
    assert "now publishes binary sensors" in caplog.text
    assert "privacy blocklist" in caplog.text


async def test_an_entry_that_already_chose_its_classes_keeps_them(hass: HomeAssistant) -> None:
    e = entry(hass, version=2, minor_version=1, data={"mode": "cloud"},
              options={CONF_INCLUDED_DOMAINS: [], CONF_EXPOSED_ENTITIES: [], CONF_INCLUDED_BINARY_SENSOR_CLASSES: []})

    assert await async_migrate_entry(hass, e)

    assert e.minor_version == 2
    assert e.options[CONF_INCLUDED_BINARY_SENSOR_CLASSES] == []


async def test_a_v1_entry_walks_both_steps(hass: HomeAssistant) -> None:
    # Pre-branch and curated: v1 → v2 clears its domains, v2.1 → v2.2 adds classes.
    e = entry(hass, version=1, minor_version=1, data={"house_id": "h1"},
              options={CONF_INCLUDED_DOMAINS: ["light", "switch"], CONF_EXPOSED_ENTITIES: ["light.hall"]})

    assert await async_migrate_entry(hass, e)

    assert (e.version, e.minor_version) == (2, 2)
    assert e.options[CONF_INCLUDED_DOMAINS] == []
    assert e.options[CONF_EXPOSED_ENTITIES] == ["light.hall"]
    assert e.options[CONF_INCLUDED_BINARY_SENSOR_CLASSES] == DEFAULT_INCLUDED_BINARY_SENSOR_CLASSES


async def test_a_current_entry_is_left_alone(hass: HomeAssistant) -> None:
    e = entry(hass, version=2, minor_version=2, data={"mode": "cloud"},
              options={CONF_INCLUDED_BINARY_SENSOR_CLASSES: ["door"]})

    assert await async_migrate_entry(hass, e)

    assert e.options[CONF_INCLUDED_BINARY_SENSOR_CLASSES] == ["door"]
