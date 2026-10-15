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


async def test_a_renamed_entity_keeps_its_registry_id(hass: HomeAssistant) -> None:
    """A rename in Home Assistant changes the entity's id and nothing else: the
    catalog says which entity it still is (BRIDGE_CLOUD_API.md §3.3)."""
    registry = er.async_get(hass)
    door = registry.async_get_or_create("lock", "test", "front-door", suggested_object_id="puerta")
    hass.states.async_set(door.entity_id, "locked", {})
    hass.states.async_set("lock.sin_registro", "locked", {})      # no registry entry: nothing to rename
    entry = bridge_entry(hass, domain_filter("lock"))

    before = {e["id"]: e for e in build_catalog(hass, entry)}
    assert before["lock.puerta"]["registry_id"] == door.id
    assert "registry_id" not in before["lock.sin_registro"]

    registry.async_update_entity(door.entity_id, new_entity_id="lock.puerta_principal")
    hass.states.async_remove("lock.puerta")
    hass.states.async_set("lock.puerta_principal", "locked", {})
    after = {e["id"]: e for e in build_catalog(hass, entry)}
    assert "lock.puerta" not in after
    assert after["lock.puerta_principal"]["registry_id"] == door.id


async def test_a_device_carries_its_connections_for_the_platform_to_match(hass: HomeAssistant) -> None:
    # BRIDGE_CLOUD_API.md §3 `device.connections` (brief 22 Q1): a MAC is how
    # the platform joins this device with a box it provisions.
    from homeassistant.helpers import device_registry as dr

    entry = bridge_entry(hass, domain_filter("light"))
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "0C:11:05:34:ED:7C"), (dr.CONNECTION_ZIGBEE, "00:12:4b:00:aa:bb:cc:dd")},
        manufacturer="Akuvox", model="S535", name="Portero",
    )
    er.async_get(hass).async_get_or_create("light", "demo", "portero-luz", suggested_object_id="portero", device_id=device.id)
    hass.states.async_set("light.portero", "on", {})

    light = next(e for e in build_catalog(hass, entry) if e["id"] == "light.portero")

    assert light["device"]["connections"] == [
        {"type": "mac", "value": "0c:11:05:34:ed:7c"},
        {"type": "zigbee", "value": "00:12:4b:00:aa:bb:cc:dd"},
    ]


async def test_a_device_with_no_connections_sends_an_empty_list(hass: HomeAssistant) -> None:
    from homeassistant.helpers import device_registry as dr

    entry = bridge_entry(hass, domain_filter("light"))
    device = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={("demo", "x")}, name="Sin red")
    er.async_get(hass).async_get_or_create("light", "demo", "sin-red", suggested_object_id="sin_red", device_id=device.id)
    hass.states.async_set("light.sin_red", "on", {})

    light = next(e for e in build_catalog(hass, entry) if e["id"] == "light.sin_red")

    assert light["device"]["connections"] == []
