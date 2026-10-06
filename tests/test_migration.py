"""Existing installations become rows, publishing what they published."""

import logging

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.turzi_bridge import async_migrate_entry, ensure_snapshot
from custom_components.turzi_bridge.const import (
    CONF_AUTO_ADD_NEW,
    CONF_CONFIG_REVISION,
    CONF_FILTER_SNAPSHOT,
    DOMAIN,
    DOOR_AND_SAFETY_CLASSES,
)
from custom_components.turzi_bridge.mqtt_bridge import TurziMqttBridge


def v2_entry(hass: HomeAssistant, options: dict, *, version: int = 2, minor: int = 1, data=None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, version=version, minor_version=minor,
        data=data if data is not None else {"mode": "cloud", "house_id": "h1", "broker": "localhost", "port": 1883},
        options=options,
    )
    entry.add_to_hass(hass)
    return entry


def rows(entry) -> list[tuple[str, dict]]:
    return sorted(
        ((s.subentry_type, dict(s.data)) for s in entry.subentries.values()),
        key=lambda r: (r[0], str(r[1])),
    )


async def test_domains_entities_and_the_blocklist_become_rows(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    entry = v2_entry(hass, {
        "included_domains": ["light", "switch"],
        "exposed_entities": ["sensor.temperatura", "input_boolean.calefon"],
        "never_expose": ["light.dormitorio"],
        "auto_add_new": True,
        CONF_CONFIG_REVISION: 4,
    })

    with caplog.at_level(logging.WARNING):
        assert await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (3, 1)
    assert rows(entry) == sorted([
        ("domain_filter", {"domain": "light", "device_classes": []}),
        ("domain_filter", {"domain": "switch", "device_classes": []}),
        ("domain_filter", {"domain": "binary_sensor", "device_classes": list(DOOR_AND_SAFETY_CLASSES)}),
        ("entity_filter", {"entities": ["sensor.temperatura", "input_boolean.calefon"]}),
        ("exclusion", {"entities": ["light.dormitorio"]}),
    ], key=lambda r: (r[0], str(r[1])))
    assert entry.options == {CONF_AUTO_ADD_NEW: True, CONF_CONFIG_REVISION: 4}
    assert "now publishes binary sensors" in caplog.text


async def test_an_entry_that_already_publishes_binary_sensors_gains_no_class_filter(hass: HomeAssistant) -> None:
    entry = v2_entry(hass, {"included_domains": ["binary_sensor"], "exposed_entities": []})

    assert await async_migrate_entry(hass, entry)

    assert rows(entry) == [("domain_filter", {"domain": "binary_sensor", "device_classes": []})]


async def test_the_unreleased_class_option_becomes_its_filter(hass: HomeAssistant) -> None:
    entry = v2_entry(
        hass, {"included_domains": [], "exposed_entities": [], "included_binary_sensor_classes": ["door"]}, minor=2
    )

    assert await async_migrate_entry(hass, entry)

    assert rows(entry) == [("domain_filter", {"domain": "binary_sensor", "device_classes": ["door"]})]


async def test_a_v1_entry_walks_both_steps(hass: HomeAssistant) -> None:
    # Pre-branch and curated: v1 → v2 clears its domains, v2 → v3 makes rows.
    entry = v2_entry(hass, {"included_domains": ["light"], "exposed_entities": ["light.hall"]}, version=1, data={"house_id": "h1"})

    assert await async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (3, 1)
    assert ("entity_filter", {"entities": ["light.hall"]}) in rows(entry)
    assert not any(r == ("domain_filter", {"domain": "light", "device_classes": []}) for r in rows(entry))


async def test_an_entry_from_a_newer_bridge_is_refused(hass: HomeAssistant) -> None:
    entry = v2_entry(hass, {}, version=4)

    assert not await async_migrate_entry(hass, entry)


async def test_automatic_exposure_off_takes_its_snapshot_at_first_start(hass: HomeAssistant) -> None:
    entry = v2_entry(hass, {"included_domains": ["light"], "exposed_entities": [], "auto_add_new": False})
    assert await async_migrate_entry(hass, entry)
    hass.states.async_set("light.hall", "on", {})
    bridge = TurziMqttBridge.from_config_entry(hass, entry)

    ensure_snapshot(hass, entry, bridge)

    assert entry.options[CONF_FILTER_SNAPSHOT] == ["light.hall"]
    assert bridge.should_expose("light.hall")
    hass.states.async_set("light.nueva", "on", {})
    assert not bridge.should_expose("light.nueva")
