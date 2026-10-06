"""The catalog is the publish scope: filter rows in, exclusions marked."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.turzi_bridge.cloud import build_catalog

from .helpers import bridge_entry, domain_filter, door_and_safety, entity_filter, exclusion


def ids(catalog) -> set[str]:
    return {e["id"] for e in catalog}


async def test_lists_what_the_rows_match_and_leaves_the_rest_out(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.puerta_principal", "off", {"device_class": "door"})
    hass.states.async_set("binary_sensor.movimiento_hall", "on", {"device_class": "motion"})
    hass.states.async_set("light.hall", "on", {})
    hass.states.async_set("switch.bomba", "off", {})
    hass.states.async_set("switch.otra", "off", {})
    hass.states.async_set("input_boolean.calefon", "off", {})
    entry = bridge_entry(hass, domain_filter("light"), door_and_safety(), entity_filter("switch.bomba", "input_boolean.calefon"))

    catalog = build_catalog(hass, entry)

    assert ids(catalog) == {"binary_sensor.puerta_principal", "light.hall", "switch.bomba", "input_boolean.calefon"}
    door = next(e for e in catalog if e["id"] == "binary_sensor.puerta_principal")
    assert door["device_class"] == "door" and door["exposed"] is True


async def test_an_excluded_entity_is_listed_as_blocked_not_published(hass: HomeAssistant) -> None:
    hass.states.async_set("light.dormitorio", "on", {})
    entry = bridge_entry(hass, domain_filter("light"), exclusion("light.dormitorio"))

    door = next(e for e in build_catalog(hass, entry) if e["id"] == "light.dormitorio")

    assert door["exposed"] is False and door["locally_blocked"] is True


async def test_an_exclusion_is_not_a_filter(hass: HomeAssistant) -> None:
    hass.states.async_set("switch.bomba", "off", {})
    entry = bridge_entry(hass, domain_filter("light"), exclusion("switch.bomba"))

    assert "switch.bomba" not in ids(build_catalog(hass, entry))


async def test_registered_sensors_follow_the_installers_show_as(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    contact = registry.async_get_or_create(
        "binary_sensor", "zigbee", "c-1", suggested_object_id="contacto_garaje", original_device_class="opening"
    )
    reclassed = registry.async_get_or_create(
        "binary_sensor", "zigbee", "c-2", suggested_object_id="contacto_deposito", original_device_class="motion"
    )
    registry.async_update_entity(reclassed.entity_id, device_class="door")

    # Neither has a state yet: the registry says what class each one is.
    catalog = build_catalog(hass, bridge_entry(hass, door_and_safety()))

    assert {contact.entity_id, reclassed.entity_id} <= ids(catalog)


async def test_no_rows_publishes_nothing(hass: HomeAssistant) -> None:
    hass.states.async_set("light.hall", "on", {})

    assert build_catalog(hass, bridge_entry(hass)) == []
