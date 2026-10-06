"""Configure is «Opciones»: automatic exposure, with what the rows publish."""

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.turzi_bridge.const import CONF_AUTO_ADD_NEW, CONF_CONFIG_REVISION, CONF_FILTER_SNAPSHOT

from .helpers import bridge_entry, domain_filter, exclusion


async def test_shows_the_counts_and_saves_without_losing_the_revision(hass: HomeAssistant) -> None:
    hass.states.async_set("light.hall", "on", {})
    hass.states.async_set("light.dormitorio", "on", {})
    entry = bridge_entry(hass, domain_filter("light"), exclusion("light.dormitorio"), options={CONF_CONFIG_REVISION: 7})

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"] == {"published": "1", "held": "1"}

    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_AUTO_ADD_NEW: False})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_AUTO_ADD_NEW] is False
    assert entry.options[CONF_CONFIG_REVISION] == 7
    assert entry.options[CONF_FILTER_SNAPSHOT] == ["light.dormitorio", "light.hall"]
