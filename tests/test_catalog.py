"""The catalog is the publish scope, door and life-safety sensors included."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.turzi_bridge.cloud import build_catalog
from custom_components.turzi_bridge.const import CONF_INCLUDED_BINARY_SENSOR_CLASSES, CONF_NEVER_EXPOSE, DOMAIN

from .helpers import cloud_options


def entry_with(hass: HomeAssistant, **options) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, version=2, minor_version=2, data={"mode": "cloud"}, options=cloud_options(**options))
    entry.add_to_hass(hass)
    return entry


def ids(catalog) -> set[str]:
    return {e["id"] for e in catalog}


async def test_lists_door_and_safety_sensors_and_leaves_motion_out(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.puerta_principal", "off", {"device_class": "door"})
    hass.states.async_set("binary_sensor.humo_cocina", "off", {"device_class": "smoke"})
    hass.states.async_set("binary_sensor.movimiento_hall", "on", {"device_class": "motion"})
    hass.states.async_set("binary_sensor.sin_clase", "off", {})
    hass.states.async_set("light.hall", "on", {})

    catalog = build_catalog(hass, entry_with(hass))

    assert ids(catalog) == {"binary_sensor.puerta_principal", "binary_sensor.humo_cocina", "light.hall"}
    door = next(e for e in catalog if e["id"] == "binary_sensor.puerta_principal")
    assert door["device_class"] == "door"
    assert door["exposed"] is True


async def test_registered_sensors_follow_the_installers_show_as(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    contact = registry.async_get_or_create(
        "binary_sensor", "zigbee", "contact-1", suggested_object_id="contacto_garaje", original_device_class="opening"
    )
    reclassed = registry.async_get_or_create(
        "binary_sensor", "zigbee", "contact-2", suggested_object_id="contacto_deposito", original_device_class="motion"
    )
    registry.async_update_entity(reclassed.entity_id, device_class="door")

    # Neither has a state yet: the registry says what class each one is.
    catalog = build_catalog(hass, entry_with(hass))

    assert {contact.entity_id, reclassed.entity_id} <= ids(catalog)


async def test_a_blocked_door_is_listed_as_blocked_not_published(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.puerta_principal", "off", {"device_class": "door"})

    catalog = build_catalog(hass, entry_with(hass, **{CONF_NEVER_EXPOSE: ["binary_sensor.puerta_principal"]}))

    door = next(e for e in catalog if e["id"] == "binary_sensor.puerta_principal")
    assert door["exposed"] is False
    assert door["locally_blocked"] is True


async def test_no_classes_lists_no_binary_sensor(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.puerta_principal", "off", {"device_class": "door"})

    catalog = build_catalog(hass, entry_with(hass, **{CONF_INCLUDED_BINARY_SENSOR_CLASSES: []}))

    assert "binary_sensor.puerta_principal" not in ids(catalog)
