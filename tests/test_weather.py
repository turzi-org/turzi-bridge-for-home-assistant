"""A community's weather: HA's weather entity published under HA's own names,
and its forecasts read with weather.get_forecasts (turzi-apps INTEGRATIONS.md
§3.10, PROTOCOL.md Service responses)."""

import json
from types import SimpleNamespace

from homeassistant.components.weather import Forecast, WeatherEntity, WeatherEntityFeature
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockPlatform, mock_platform

from custom_components.turzi_bridge.const import DEFAULT_FILTERS, SELECTABLE_DOMAINS
from custom_components.turzi_bridge.mqtt_bridge import TurziMqttBridge

from .helpers import HOUSE, FakeClient, bridge_entry, domain_filter

WEATHER = "weather.forecast_home"
FORECAST = [{"datetime": "2026-10-13T12:00:00+00:00", "condition": "rainy", "temperature": 17.0, "templow": 11.0}]

HA_WEATHER_ATTRIBUTES = {
    "temperature": 18.4,
    "apparent_temperature": 17.9,
    "dew_point": 12.1,
    "humidity": 67,
    "cloud_coverage": 40,
    "uv_index": 3.2,
    "pressure": 1016.2,
    "wind_bearing": 225.0,
    "wind_gust_speed": 31.0,
    "wind_speed": 14.8,
    "visibility": 10.0,
    "temperature_unit": "°C",
    "pressure_unit": "hPa",
    "wind_speed_unit": "km/h",
    "visibility_unit": "km",
    "precipitation_unit": "mm",
    "attribution": "Weather forecast from met.no",
    "supported_features": 3,
}


def make_bridge(hass: HomeAssistant, *rows) -> TurziMqttBridge:
    bridge = TurziMqttBridge.from_config_entry(hass, bridge_entry(hass, *rows))
    bridge._client = FakeClient()
    return bridge


def published(bridge: TurziMqttBridge, entity_id: str) -> dict:
    domain, slug = entity_id.split(".", 1)
    topic = f"house/{HOUSE}/state/{domain}/{slug}"
    return json.loads(next(p for t, p, _ in bridge._client.publishes if t == topic))


def ack(bridge: TurziMqttBridge, command_id: str) -> dict:
    return json.loads(next(p for t, p, _ in bridge._client.publishes if t == f"house/{HOUSE}/ack/{command_id}"))


async def command(bridge: TurziMqttBridge, entity_id: str, payload: dict) -> None:
    domain, slug = entity_id.split(".", 1)
    message = SimpleNamespace(payload=json.dumps({"metadata": {"user_name": "Ana"}, **payload}).encode())
    await bridge._handle_command(f"house/{HOUSE}/command/{domain}/{slug}", message)


def logbook_calls(hass: HomeAssistant) -> list[ServiceCall]:
    calls: list[ServiceCall] = []

    async def log(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("logbook", "log", log)
    return calls


def test_weather_is_offered_but_not_exposed_by_default() -> None:
    assert "weather" in SELECTABLE_DOMAINS
    assert all(row.get("domain") != "weather" for row in DEFAULT_FILTERS)


async def test_a_weather_entity_publishes_its_condition_and_has_names(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass, domain_filter("weather"))
    bridge._setup_state_listener()

    hass.states.async_set(WEATHER, "partlycloudy", {**HA_WEATHER_ATTRIBUTES, "friendly_name": "Casa"})
    await hass.async_block_till_done()

    payload = published(bridge, WEATHER)
    assert payload["state"] == "partlycloudy"
    # The air's temperature keeps its name: only a climate's is a setpoint.
    assert payload["attributes"] == HA_WEATHER_ATTRIBUTES


async def test_a_climate_still_publishes_its_setpoint_as_target_temperature(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass, domain_filter("climate"))
    bridge._setup_state_listener()

    hass.states.async_set("climate.living", "heat", {"temperature": 21.5, "current_temperature": 19.0})
    await hass.async_block_till_done()

    attributes = published(bridge, "climate.living")["attributes"]
    assert attributes["target_temperature"] == 21.5
    assert "temperature" not in attributes


async def test_a_water_heater_publishes_its_setpoint_as_target_temperature(hass: HomeAssistant) -> None:
    """HA names a water heater's setpoint `temperature`; the protocol, `target_temperature`.

    The map listed `target_temperature`, an attribute HA never sets, so no
    water heater ever published its setpoint.
    """
    bridge = make_bridge(hass, domain_filter("water_heater"))
    bridge._setup_state_listener()

    hass.states.async_set("water_heater.termo", "eco", {"temperature": 55.0, "current_temperature": 48.0})
    await hass.async_block_till_done()

    assert published(bridge, "water_heater.termo")["attributes"] == {"target_temperature": 55.0, "current_temperature": 48.0}


async def test_get_forecasts_returns_the_entity_forecast_in_the_executed_ack(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass, domain_filter("weather"))
    hass.states.async_set(WEATHER, "sunny", HA_WEATHER_ATTRIBUTES)
    logbook = logbook_calls(hass)
    asked: list[dict] = []

    async def get_forecasts(call: ServiceCall) -> dict:
        asked.append(dict(call.data))
        return {WEATHER: {"forecast": FORECAST}, "weather.other": {"forecast": []}}

    hass.services.async_register("weather", "get_forecasts", get_forecasts, supports_response=SupportsResponse.ONLY)

    await command(bridge, WEATHER, {"command": "weather.get_forecasts", "command_id": "c1", "parameters": {"type": "daily"}})

    assert ack(bridge, "c1") | {"timestamp": 0} == {
        "command_id": "c1",
        "status": "executed",
        "reason": None,
        "timestamp": 0,
        "response": {"forecast": FORECAST},
    }
    assert asked == [{"entity_id": [WEATHER], "type": "daily"}]
    # A forecast asked for is no action anyone took.
    assert logbook == []


async def test_a_read_that_returns_nothing_for_the_entity_fails(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass, domain_filter("weather"))
    hass.states.async_set(WEATHER, "sunny", HA_WEATHER_ATTRIBUTES)

    async def get_forecasts(call: ServiceCall) -> dict:
        return {"weather.other": {"forecast": FORECAST}}

    hass.services.async_register("weather", "get_forecasts", get_forecasts, supports_response=SupportsResponse.ONLY)

    await command(bridge, WEATHER, {"command": "weather.get_forecasts", "command_id": "c2", "parameters": {"type": "hourly"}})

    assert ack(bridge, "c2")["status"] == "failed"
    assert ack(bridge, "c2")["reason"] == "unsupported_command"
    assert "response" not in ack(bridge, "c2")


async def test_a_forecast_the_platform_refuses_is_a_platform_error(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass, domain_filter("weather"))
    hass.states.async_set(WEATHER, "sunny", HA_WEATHER_ATTRIBUTES)

    async def get_forecasts(call: ServiceCall) -> dict:
        raise HomeAssistantError("Weather entity does not support 'hourly' forecast")

    hass.services.async_register("weather", "get_forecasts", get_forecasts, supports_response=SupportsResponse.ONLY)

    await command(bridge, WEATHER, {"command": "weather.get_forecasts", "command_id": "c3", "parameters": {"type": "hourly"}})

    assert (ack(bridge, "c3")["status"], ack(bridge, "c3")["reason"]) == ("failed", "platform_error")


async def test_a_service_this_ha_does_not_have_is_unsupported(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass, domain_filter("weather"))
    hass.states.async_set(WEATHER, "sunny", HA_WEATHER_ATTRIBUTES)

    await command(bridge, WEATHER, {"command": "weather.get_forecasts", "command_id": "c4", "parameters": {"type": "daily"}})

    assert (ack(bridge, "c4")["status"], ack(bridge, "c4")["reason"]) == ("failed", "unsupported_command")


async def test_an_action_still_acks_without_a_response_and_is_logged(hass: HomeAssistant) -> None:
    bridge = make_bridge(hass, domain_filter("light"))
    hass.states.async_set("light.hall", "off", {})
    logbook = logbook_calls(hass)
    turned_on: list[ServiceCall] = []

    async def turn_on(call: ServiceCall) -> None:
        turned_on.append(call)

    hass.services.async_register("light", "turn_on", turn_on)

    await command(bridge, "light.hall", {"command": "light.turn_on", "command_id": "c5"})

    assert ack(bridge, "c5")["status"] == "executed"
    assert "response" not in ack(bridge, "c5")
    assert len(turned_on) == 1 and len(logbook) == 1


class Casa(WeatherEntity):
    """A weather entity with daily forecasts only, through HA's own component."""

    _attr_name = "Casa"
    _attr_condition = "sunny"
    _attr_native_temperature = 18.4
    _attr_native_temperature_unit = "°C"
    _attr_humidity = 67
    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY

    async def async_forecast_daily(self) -> list[Forecast]:
        return [Forecast(datetime="2026-10-13T12:00:00+00:00", condition="rainy", native_temperature=17.0, native_templow=11.0)]


async def test_home_assistants_own_weather_component_end_to_end(hass: HomeAssistant) -> None:
    """The shapes above are HA's: its weather component, not a stand-in service."""

    async def setup_platform(hass, config, async_add_entities, discovery_info=None) -> None:
        async_add_entities([Casa()])

    bridge = make_bridge(hass, domain_filter("weather"))
    bridge._setup_state_listener()
    mock_platform(hass, "test.weather", MockPlatform(async_setup_platform=setup_platform))
    assert await async_setup_component(hass, "weather", {"weather": {"platform": "test"}})
    await hass.async_block_till_done()

    payload = published(bridge, "weather.casa")
    assert payload["state"] == "sunny"
    assert payload["attributes"]["temperature"] == 18.4
    assert payload["attributes"]["temperature_unit"] == "°C"
    assert payload["attributes"]["supported_features"] == 1

    await command(bridge, "weather.casa", {"command": "weather.get_forecasts", "command_id": "d", "parameters": {"type": "daily"}})
    await command(bridge, "weather.casa", {"command": "weather.get_forecasts", "command_id": "h", "parameters": {"type": "hourly"}})

    assert ack(bridge, "d")["response"] == {
        "forecast": [{"datetime": "2026-10-13T12:00:00+00:00", "condition": "rainy", "temperature": 17.0, "templow": 11.0}]
    }
    # It has no hourly forecast: HA refuses, and the ack says so.
    assert (ack(bridge, "h")["status"], ack(bridge, "h")["reason"]) == ("failed", "platform_error")
