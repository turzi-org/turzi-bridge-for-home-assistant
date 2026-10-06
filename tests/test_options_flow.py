"""The installer sees and edits the classes in Exposure & privacy."""

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.turzi_bridge.config_flow import TurziAppConnectorConfigFlow, _default_options
from custom_components.turzi_bridge.const import (
    CONF_CONFIG_REVISION,
    CONF_INCLUDED_BINARY_SENSOR_CLASSES,
    DEFAULT_INCLUDED_BINARY_SENSOR_CLASSES,
    DOMAIN,
)

from .helpers import cloud_options


async def test_new_entries_start_with_the_classes_in_both_modes(hass: HomeAssistant) -> None:
    for cloud in (True, False):
        assert _default_options(hass, cloud=cloud)[CONF_INCLUDED_BINARY_SENSOR_CLASSES] == DEFAULT_INCLUDED_BINARY_SENSOR_CLASSES
    assert (TurziAppConnectorConfigFlow.VERSION, TurziAppConnectorConfigFlow.MINOR_VERSION) == (2, 2)


async def test_the_form_shows_the_classes_and_saves_an_edit_without_losing_the_revision(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, minor_version=2, data={"mode": "cloud"},
        options=cloud_options(**{CONF_CONFIG_REVISION: 7}),
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    field = next(k for k in result["data_schema"].schema if k == CONF_INCLUDED_BINARY_SENSOR_CLASSES)
    assert field.default() == DEFAULT_INCLUDED_BINARY_SENSOR_CLASSES

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "included_domains": ["light"],
            CONF_INCLUDED_BINARY_SENSOR_CLASSES: ["door", "smoke"],
            "exposed_entities": [],
            "auto_add_new": True,
            "never_expose": [],
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_INCLUDED_BINARY_SENSOR_CLASSES] == ["door", "smoke"]
    assert entry.options[CONF_CONFIG_REVISION] == 7
