"""MQTT Bridge for the Turzi App Connector integration.

This module implements the MQTT transport binding of the Turzi Protocol.
It manages the connection to an external MQTT broker and handles:
- Publishing HA entity state changes to the app
- Receiving commands from the app and calling HA services
- Heartbeat ping/pong
- Full state reload (app-initiated or input_boolean triggered)
- Cleanup of MQTT retained messages when entities are excluded
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import ssl
from datetime import datetime, timezone
from typing import Any

import aiomqtt

from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    ALARM_MODE_MAP,
    CONF_AUTO_ADD_NEW,
    CONF_BROKER,
    CONF_EXPOSED_ENTITIES,
    CONF_HOUSE_ID,
    CONF_INCLUDED_DOMAINS,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USE_TLS,
    CONF_USERNAME,
    DEFAULT_AUTO_ADD_NEW,
    DEFAULT_INCLUDED_DOMAINS,
    DOMAIN,
    DOMAIN_ATTRIBUTES,
    SIGNAL_CONFIG_UPDATED,
)

_LOGGER = logging.getLogger(__name__)

# Reconnection backoff parameters
_RECONNECT_MIN_DELAY = 5
_RECONNECT_MAX_DELAY = 60
_RECONNECT_BACKOFF_FACTOR = 2


class TurziMqttBridge:
    """Manages the MQTT connection and message routing between HA and Turzi app."""

    def __init__(
        self,
        hass: HomeAssistant,
        broker: str,
        port: int,
        username: str | None,
        password: str | None,
        house_id: str,
        use_tls: bool,
        entry_id: str,
        exposed_entities: list[str],
        included_domains: list[str],
        auto_add_new: bool,
    ) -> None:
        """Initialize the MQTT bridge."""
        self.hass = hass
        self._broker = broker
        self._port = port
        self._username = username or None
        self._password = password or None
        self._house_id = house_id
        self._use_tls = use_tls
        self._entry_id = entry_id
        self._exposed_entities: set[str] = set(exposed_entities)
        self._included_domains: set[str] = set(included_domains)
        self._auto_add_new: bool = auto_add_new

        # Internal state
        self._client: aiomqtt.Client | None = None
        self._connection_task: asyncio.Task | None = None
        self._unsub_state_listener: callback | None = None
        self._unsub_reload_listener: callback | None = None
        self._unsub_registry_listener: callback | None = None
        self._stopping = False

        # Track entity_ids that have been published to MQTT (for cleanup)
        self._published_entities: set[str] = set()

    @classmethod
    def from_config_entry(cls, hass: HomeAssistant, entry) -> TurziMqttBridge:
        """Create a TurziMqttBridge from a config entry."""
        return cls(
            hass=hass,
            broker=entry.data[CONF_BROKER],
            port=entry.data[CONF_PORT],
            username=entry.data.get(CONF_USERNAME),
            password=entry.data.get(CONF_PASSWORD),
            house_id=entry.data[CONF_HOUSE_ID],
            use_tls=entry.data.get(CONF_USE_TLS, False),
            entry_id=entry.entry_id,
            exposed_entities=entry.options.get(CONF_EXPOSED_ENTITIES, []),
            included_domains=entry.options.get(CONF_INCLUDED_DOMAINS, DEFAULT_INCLUDED_DOMAINS),
            auto_add_new=entry.options.get(CONF_AUTO_ADD_NEW, DEFAULT_AUTO_ADD_NEW),
        )

    # -------------------------------------------------------------------------
    # Entity exposure (simple set membership)
    # -------------------------------------------------------------------------

    def should_expose(self, entity_id: str) -> bool:
        """Return True if entity_id is in the exposed set."""
        return entity_id in self._exposed_entities

    def update_config(
        self,
        exposed_entities: list[str],
        included_domains: list[str],
        auto_add_new: bool,
    ) -> None:
        """Apply updated config and sync MQTT state accordingly."""
        old_exposed = set(self._published_entities)

        self._exposed_entities = set(exposed_entities)
        self._included_domains = set(included_domains)
        self._auto_add_new = auto_add_new

        new_exposed: set[str] = {
            s.entity_id
            for s in self.hass.states.async_all()
            if self.should_expose(s.entity_id)
        }

        to_add = new_exposed - old_exposed
        to_remove = old_exposed - new_exposed

        if self._client is not None:
            for entity_id in to_add:
                state = self.hass.states.get(entity_id)
                if state:
                    self.hass.async_create_task(
                        self._publish_state(self._client, state),
                        f"turzi_publish_new_{entity_id}",
                    )
            for entity_id in to_remove:
                self.hass.async_create_task(
                    self._remove_entity_from_mqtt(self._client, entity_id),
                    f"turzi_remove_{entity_id}",
                )

    async def _persist_exposed_entities(self) -> None:
        """Persist the current exposed_entities set to config entry options."""
        from homeassistant.helpers.dispatcher import async_dispatcher_send

        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return
        new_options = {**entry.options, CONF_EXPOSED_ENTITIES: list(self._exposed_entities)}
        self.hass.config_entries.async_update_entry(entry, options=new_options)
        async_dispatcher_send(self.hass, SIGNAL_CONFIG_UPDATED)

    # -------------------------------------------------------------------------
    # Attribute extraction
    # -------------------------------------------------------------------------

    @staticmethod
    def _extract_attributes(domain: str, state: State) -> dict[str, Any] | None:
        """Extract domain-specific attributes from a state object.

        Uses the DOMAIN_ATTRIBUTES mapping from the Turzi Protocol spec.
        Returns None if no attributes are defined or all values are null.
        """
        attr_keys = DOMAIN_ATTRIBUTES.get(domain)
        if not attr_keys:
            return None

        attributes: dict[str, Any] = {}
        for key in attr_keys:
            value = state.attributes.get(key)
            if value is not None:
                attributes[key] = value

        return attributes if attributes else None

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def async_start(self) -> None:
        """Start the MQTT bridge."""
        self._stopping = False
        self._setup_state_listener()
        self._setup_reload_listener()
        self._setup_registry_listener()
        self._connection_task = self.hass.async_create_task(
            self._connection_loop(), "turzi_mqtt_connection_loop"
        )

    async def async_stop(self) -> None:
        """Stop the MQTT bridge and clean up all resources."""
        self._stopping = True

        # Unsubscribe from HA events
        if self._unsub_state_listener:
            self._unsub_state_listener()
            self._unsub_state_listener = None

        if self._unsub_reload_listener:
            self._unsub_reload_listener()
            self._unsub_reload_listener = None

        if self._unsub_registry_listener:
            self._unsub_registry_listener()
            self._unsub_registry_listener = None

        # Cancel the connection task
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()
            try:
                await self._connection_task
            except asyncio.CancelledError:
                pass
            self._connection_task = None

        _LOGGER.info("Turzi MQTT bridge stopped for house '%s'", self._house_id)

    # -------------------------------------------------------------------------
    # Entity registry listener (live label sync)
    # -------------------------------------------------------------------------

    def _setup_registry_listener(self) -> None:
        """Watch entity registry for auto-add (new entities) and removal cleanup."""

        @callback
        def _on_registry_updated(event: Event) -> None:
            action = event.data.get("action")
            entity_id = event.data.get("entity_id")
            if not entity_id:
                return

            if action == "create" and self._auto_add_new:
                # Auto-add new entity if its domain is in included_domains
                domain = entity_id.split(".")[0]
                if domain not in self._included_domains:
                    return
                reg = er.async_get(self.hass)
                reg_entry = reg.async_get(entity_id)
                if reg_entry is None or reg_entry.disabled_by:
                    return
                if entity_id in self._exposed_entities:
                    return
                _LOGGER.debug("Auto-adding new entity %s (domain: %s)", entity_id, domain)
                self._exposed_entities.add(entity_id)
                # Publish immediately
                state = self.hass.states.get(entity_id)
                if state and self._client is not None:
                    self.hass.async_create_task(
                        self._publish_state(self._client, state),
                        f"turzi_publish_new_{entity_id}",
                    )
                # Persist asynchronously
                self.hass.async_create_task(
                    self._persist_exposed_entities(),
                    "turzi_persist_exposed_entities",
                )

            elif action == "remove":
                if entity_id in self._published_entities and self._client is not None:
                    self.hass.async_create_task(
                        self._remove_entity_from_mqtt(self._client, entity_id),
                        f"turzi_remove_{entity_id}",
                    )
                self._exposed_entities.discard(entity_id)

        self._unsub_registry_listener = self.hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED, _on_registry_updated
        )


    # -------------------------------------------------------------------------
    # MQTT connection loop with auto-reconnect
    # -------------------------------------------------------------------------

    async def _connection_loop(self) -> None:
        """Maintain the MQTT connection with exponential backoff reconnect."""
        reconnect_delay = _RECONNECT_MIN_DELAY

        while not self._stopping:
            try:
                tls_params = ssl.create_default_context() if self._use_tls else None

                async with aiomqtt.Client(
                    hostname=self._broker,
                    port=self._port,
                    username=self._username,
                    password=self._password,
                    tls_params=tls_params,
                    keepalive=60,
                ) as client:
                    self._client = client
                    reconnect_delay = _RECONNECT_MIN_DELAY  # Reset on success
                    _LOGGER.info(
                        "Connected to MQTT broker %s:%s for house '%s'",
                        self._broker,
                        self._port,
                        self._house_id,
                    )

                    # Subscribe to incoming topics
                    await self._subscribe_topics(client)

                    # Publish initial states for all exposed entities
                    await self._publish_all_current_states(client)

                    # Listen for incoming messages
                    async for message in client.messages:
                        await self._handle_message(message)

            except aiomqtt.MqttError as err:
                self._client = None
                if self._stopping:
                    break
                _LOGGER.warning(
                    "MQTT connection lost for house '%s': %s. "
                    "Reconnecting in %ds...",
                    self._house_id,
                    err,
                    reconnect_delay,
                )
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(
                    reconnect_delay * _RECONNECT_BACKOFF_FACTOR,
                    _RECONNECT_MAX_DELAY,
                )

            except asyncio.CancelledError:
                self._client = None
                break

            except Exception:  # noqa: BLE001
                self._client = None
                if self._stopping:
                    break
                _LOGGER.exception(
                    "Unexpected error in MQTT connection loop for house '%s'. "
                    "Reconnecting in %ds...",
                    self._house_id,
                    reconnect_delay,
                )
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(
                    reconnect_delay * _RECONNECT_BACKOFF_FACTOR,
                    _RECONNECT_MAX_DELAY,
                )

    async def _subscribe_topics(self, client: aiomqtt.Client) -> None:
        """Subscribe to all incoming MQTT topics."""
        # Commands from app: house/{id}/command/#
        command_topic = f"house/{self._house_id}/command/#"
        await client.subscribe(command_topic, qos=0)
        _LOGGER.debug("Subscribed to %s", command_topic)

        # Heartbeat ping: house/{id}/app/command/heartbeat
        heartbeat_topic = f"house/{self._house_id}/app/command/heartbeat"
        await client.subscribe(heartbeat_topic, qos=1)
        _LOGGER.debug("Subscribed to %s", heartbeat_topic)

        # App reload request: house/{id}/app/command/reload
        reload_topic = f"house/{self._house_id}/app/command/reload"
        await client.subscribe(reload_topic, qos=1)
        _LOGGER.debug("Subscribed to %s", reload_topic)

    async def _publish_all_current_states(self, client: aiomqtt.Client) -> None:
        """Publish the current state of all exposed entities.

        Called on initial connect and on reload requests.
        """
        count = 0
        states = self.hass.states.async_all()
        for state in states:
            if self.should_expose(state.entity_id):
                await self._publish_state(client, state)
                count += 1
        _LOGGER.info(
            "Published %d entity states for house '%s'",
            count,
            self._house_id,
        )

    # -------------------------------------------------------------------------
    # State publishing (HA → App)
    # -------------------------------------------------------------------------

    def _setup_state_listener(self) -> None:
        """Set up the HA state change listener."""

        @callback
        def _on_state_changed(event: Event[EventStateChangedData]) -> None:
            """Handle a state change event."""
            new_state = event.data.get("new_state")
            if new_state is None:
                return

            entity_id = event.data["entity_id"]
            if not self.should_expose(entity_id):
                return

            if self._client is not None:
                self.hass.async_create_task(
                    self._publish_state(self._client, new_state),
                    f"turzi_publish_{entity_id}",
                )

        # Listen to ALL state changes (filtered in the callback)
        self._unsub_state_listener = self.hass.bus.async_listen(
            "state_changed", _on_state_changed
        )

    async def _publish_state(
        self, client: aiomqtt.Client, state: State
    ) -> None:
        """Publish an entity state update to MQTT."""
        entity_id = state.entity_id
        domain = entity_id.split(".")[0]
        entity_slug = entity_id.split(".", 1)[1]

        topic = f"house/{self._house_id}/state/{domain}/{entity_slug}"

        # Build the Turzi Protocol state payload
        payload: dict[str, Any] = {
            "state": state.state,
            "last_changed": state.last_changed.isoformat(),
            "timestamp": math.floor(datetime.now(tz=timezone.utc).timestamp()),
        }

        # Extract domain-specific attributes
        attributes = self._extract_attributes(domain, state)
        if attributes:
            payload["attributes"] = attributes

        try:
            await client.publish(
                topic,
                payload=json.dumps(payload),
                qos=1,
                retain=True,
            )
            self._published_entities.add(entity_id)
        except aiomqtt.MqttError:
            _LOGGER.warning("Failed to publish state for %s", entity_id)

    async def _remove_entity_from_mqtt(
        self, client: aiomqtt.Client, entity_id: str
    ) -> None:
        """Remove an entity's retained message from MQTT.

        Publishing an empty payload with retain=True clears the retained message.
        """
        domain = entity_id.split(".")[0]
        entity_slug = entity_id.split(".", 1)[1]
        topic = f"house/{self._house_id}/state/{domain}/{entity_slug}"

        try:
            await client.publish(
                topic,
                payload="",
                qos=1,
                retain=True,
            )
            self._published_entities.discard(entity_id)
            _LOGGER.debug("Removed MQTT retained message for %s", entity_id)
        except aiomqtt.MqttError:
            _LOGGER.warning("Failed to remove MQTT message for %s", entity_id)

    # -------------------------------------------------------------------------
    # Command handling (App → HA)
    # -------------------------------------------------------------------------

    async def _handle_message(self, message: aiomqtt.Message) -> None:
        """Route an incoming MQTT message to the appropriate handler."""
        topic = str(message.topic)

        # Heartbeat ping
        if topic == f"house/{self._house_id}/app/command/heartbeat":
            await self._handle_heartbeat()
            return

        # App-initiated reload request
        if topic == f"house/{self._house_id}/app/command/reload":
            await self._handle_reload_request()
            return

        # Command from app: house/{id}/command/{domain}/{entity_slug}
        prefix = f"house/{self._house_id}/command/"
        if topic.startswith(prefix):
            await self._handle_command(topic, message)
            return

        _LOGGER.debug("Received message on unhandled topic: %s", topic)

    async def _handle_command(
        self, topic: str, message: aiomqtt.Message
    ) -> None:
        """Process a command from the Turzi app."""
        # Parse topic: house/{id}/command/{domain}/{entity_slug}
        topic_parts = topic.split("/")
        if len(topic_parts) < 5 or topic_parts[2] != "command":
            _LOGGER.error("Invalid command topic format: %s", topic)
            return

        try:
            payload = json.loads(message.payload)
        except (json.JSONDecodeError, TypeError):
            _LOGGER.error("Invalid JSON payload on topic %s", topic)
            return

        if "command" not in payload:
            _LOGGER.error("Missing 'command' field in payload on topic %s", topic)
            return

        domain = topic_parts[3]
        entity_slug = topic_parts[4]
        entity_id = f"{domain}.{entity_slug}"
        command = payload["command"]
        parameters = payload.get("parameters", {})
        metadata = payload.get("metadata", {})
        user_name = metadata.get("user_name", "Unknown")
        user_email = metadata.get("user_email", "")

        # Special handling for alarm_control_panel
        if domain == "alarm_control_panel":
            alarm_mode = parameters.get("alarm_mode")
            if alarm_mode and alarm_mode in ALARM_MODE_MAP:
                command = f"alarm_control_panel.{ALARM_MODE_MAP[alarm_mode]}"
                parameters = None  # Alarm commands don't pass parameters

        # Split command into domain.action
        if "." in command:
            service_domain, service_action = command.split(".", 1)
        else:
            _LOGGER.error("Invalid command format (expected domain.action): %s", command)
            return

        # Build service data
        service_data: dict[str, Any] = {
            "entity_id": [entity_id],
        }
        if parameters:
            service_data.update(parameters)

        # Log to HA logbook
        try:
            await self.hass.services.async_call(
                "logbook",
                "log",
                {
                    "name": entity_slug,
                    "entity_id": entity_id,
                    "message": f"turzi App - {user_name} ({service_action})",
                },
            )
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to log to logbook for %s", entity_id)

        # Small delay before executing the command (matches Node-RED flow)
        await asyncio.sleep(0.1)

        # Call the HA service
        try:
            await self.hass.services.async_call(
                service_domain,
                service_action,
                service_data,
                blocking=False,
            )
            _LOGGER.info(
                "Executed command %s.%s for %s (by %s <%s>)",
                service_domain,
                service_action,
                entity_id,
                user_name,
                user_email,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "Failed to execute command %s.%s for %s",
                service_domain,
                service_action,
                entity_id,
            )

    # -------------------------------------------------------------------------
    # Heartbeat (ping/pong)
    # -------------------------------------------------------------------------

    async def _handle_heartbeat(self) -> None:
        """Respond to a heartbeat ping with a pong."""
        if self._client is None:
            return

        topic = f"house/{self._house_id}/app/state/heartbeat"
        payload = {
            "state": "pong",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

        try:
            await self._client.publish(
                topic,
                payload=json.dumps(payload),
                qos=1,
                retain=False,
            )
            _LOGGER.debug("Heartbeat pong sent for house '%s'", self._house_id)
        except aiomqtt.MqttError:
            _LOGGER.warning("Failed to send heartbeat pong")

    # -------------------------------------------------------------------------
    # Reload (full state re-publish)
    # -------------------------------------------------------------------------

    async def _handle_reload_request(self) -> None:
        """Handle an app-initiated reload request.

        The app publishes to house/{id}/app/command/reload to request
        a full re-send of all exposed entity states.
        """
        if self._client is None:
            return

        _LOGGER.info(
            "Reload requested by app for house '%s' — re-publishing all states",
            self._house_id,
        )
        await self._publish_all_current_states(self._client)

    def _setup_reload_listener(self) -> None:
        """Listen for input_boolean.app_reload_house_structure turning on.

        When triggered, re-publishes all exposed entity states to MQTT.
        """
        reload_entity = "input_boolean.app_reload_house_structure"

        @callback
        def _on_reload_changed(event: Event[EventStateChangedData]) -> None:
            """Handle the reload input_boolean turning on."""
            new_state = event.data.get("new_state")
            if new_state is None or new_state.state != "on":
                return

            if self._client is not None:
                _LOGGER.info(
                    "Reload triggered via input_boolean for house '%s'",
                    self._house_id,
                )
                self.hass.async_create_task(
                    self._publish_all_current_states(self._client),
                    "turzi_reload_all_states",
                )

        self._unsub_reload_listener = async_track_state_change_event(
            self.hass, [reload_entity], _on_reload_changed
        )
