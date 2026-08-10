"""MQTT Bridge for the turzi Bridge integration.

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
import collections
import json
import logging
import math
import ssl
from datetime import datetime, timezone
from typing import Any

import aiomqtt

from homeassistant.core import (
    Context,
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
    CLOCK_SKEW_TOLERANCE_SECONDS,
    CONF_AUTO_ADD_NEW,
    CONF_BROKER,
    CONF_EXPOSED_ENTITIES,
    CONF_HOUSE_ID,
    CONF_INCLUDED_DOMAINS,
    CONF_NEVER_EXPOSE,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USE_TLS,
    CONF_USERNAME,
    DEFAULT_AUTO_ADD_NEW,
    DEFAULT_INCLUDED_DOMAINS,
    DEFAULT_TTL_CEILING_SECONDS,
    DOMAIN,
    DOMAIN_ATTRIBUTES,
    HA_TO_PROTOCOL_KEY,
    PROTOCOL_VERSION,
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
        never_expose: list[str] | None = None,
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
        # Privacy floor: never published, in any mode; wins over everything.
        self._never_expose: set[str] = set(never_expose or [])

        # Internal state
        self._client: aiomqtt.Client | None = None
        self._connection_task: asyncio.Task | None = None
        self._unsub_state_listener: callback | None = None
        self._unsub_reload_listener: callback | None = None
        self._unsub_registry_listener: callback | None = None
        self._stopping = False

        # Track entity_ids that have been published to MQTT (for cleanup)
        self._published_entities: set[str] = set()

        # Protocol v1.1 — command dedupe: command_id -> monotonic receipt time.
        # Retention must be >= the TTL ceiling (PROTOCOL v1.1 §2) or a late
        # duplicate could pass both dedupe and expiry and actuate twice.
        self._seen_command_ids: dict[str, float] = {}
        # Protocol v1.1 — origin attribution: HA context.id -> command_id for
        # service calls made by this bridge, so resulting state changes are
        # tagged origin.type="turzi" with exact command correlation (§4).
        self._command_contexts: dict[str, str] = {}

        # Remote exposure config (cloud mode): set by __init__ when the entry
        # supports it. Callback receives the parsed config/exposure payload;
        # config_revision is reported in the retained availability payload.
        self.exposure_callback = None
        self.config_revision: int | None = None

        # Status tracking (exposed via turzi/status WebSocket)
        self._connection_status: str = "connecting"
        self._reconnect_count: int = 0
        self._last_connect_time: datetime | None = None
        self._last_disconnect_time: datetime | None = None
        self._event_log: collections.deque = collections.deque(maxlen=50)

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
            never_expose=entry.options.get(CONF_NEVER_EXPOSE, []),
        )

    # -------------------------------------------------------------------------
    # Entity exposure (simple set membership)
    # -------------------------------------------------------------------------

    def should_expose(self, entity_id: str) -> bool:
        """Effective exposure: included domains expose wholesale; the
        exposed_entities list holds MANUAL additions only; the privacy
        blocklist wins over everything."""
        if entity_id in self._never_expose:
            return False
        if entity_id in self._exposed_entities:
            return True
        return entity_id.split(".")[0] in self._included_domains

    def get_status(self) -> dict:
        """Return a status snapshot for the panel Status tab."""
        return {
            "status": self._connection_status,
            "broker": self._broker,
            "port": self._port,
            "house_id": self._house_id,
            "use_tls": self._use_tls,
            "reconnect_count": self._reconnect_count,
            "last_connect_time": self._last_connect_time.isoformat() if self._last_connect_time else None,
            "last_disconnect_time": self._last_disconnect_time.isoformat() if self._last_disconnect_time else None,
            "published_count": len(self._published_entities),
            "exposed_count": len(self._exposed_entities),
            "event_log": list(self._event_log),
        }

    def _log_event(self, level: str, message: str) -> None:
        """Append an event to the ring-buffer log and notify the panel."""
        self._event_log.append({
            "time": datetime.now(tz=timezone.utc).isoformat(),
            "level": level,
            "message": message,
        })
        from homeassistant.helpers.dispatcher import async_dispatcher_send
        async_dispatcher_send(self.hass, SIGNAL_CONFIG_UPDATED)

    def update_config(
        self,
        exposed_entities: list[str],
        included_domains: list[str],
        auto_add_new: bool,
        never_expose: list[str] | None = None,
    ) -> None:
        """Apply updated config and sync MQTT state accordingly.

        Entities leaving the effective exposed set (including newly
        privacy-blocked ones) get their retained state cleaned up.
        """
        old_exposed = set(self._published_entities)

        self._exposed_entities = set(exposed_entities)
        self._included_domains = set(included_domains)
        self._auto_add_new = auto_add_new
        self._never_expose = set(never_expose or [])

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

    # -------------------------------------------------------------------------
    # Attribute extraction
    # -------------------------------------------------------------------------

    @staticmethod
    def _extract_attributes(domain: str, state: State) -> dict[str, Any] | None:
        """Extract domain-specific attributes from a state object.

        Uses the DOMAIN_ATTRIBUTES mapping from the Turzi Protocol spec.
        HA attribute names are renamed to protocol names via HA_TO_PROTOCOL_KEY.
        Returns None if no attributes are defined or all values are null.
        """
        attr_keys = DOMAIN_ATTRIBUTES.get(domain)
        if not attr_keys:
            return None

        attributes: dict[str, Any] = {}
        for ha_key in attr_keys:
            value = state.attributes.get(ha_key)
            if value is not None:
                protocol_key = HA_TO_PROTOCOL_KEY.get(ha_key, ha_key)
                attributes[protocol_key] = value

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

        # Graceful availability: overwrite the retained LWT payload so clients
        # see a deliberate shutdown instead of waiting on broker keepalive.
        if self._client is not None:
            try:
                await self._client.publish(
                    f"house/{self._house_id}/availability",
                    payload=json.dumps({"state": "offline", "reason": "shutdown"}),
                    qos=1,
                    retain=True,
                )
            except aiomqtt.MqttError:
                _LOGGER.debug("Could not publish graceful offline availability")

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
                # Domain inclusion exposes new entities inherently; just
                # publish the initial state immediately.
                if not self.should_expose(entity_id):
                    return
                reg = er.async_get(self.hass)
                reg_entry = reg.async_get(entity_id)
                if reg_entry is None or reg_entry.disabled_by:
                    return
                _LOGGER.debug("Publishing newly created entity %s", entity_id)
                state = self.hass.states.get(entity_id)
                if state and self._client is not None:
                    self.hass.async_create_task(
                        self._publish_state(self._client, state),
                        f"turzi_publish_new_{entity_id}",
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
        from homeassistant.helpers.dispatcher import async_dispatcher_send

        reconnect_delay = _RECONNECT_MIN_DELAY
        self._connection_status = "connecting"
        self._log_event("info", f"Connecting to {self._broker}:{self._port}…")

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
                    will=aiomqtt.Will(
                        topic=f"house/{self._house_id}/availability",
                        payload=json.dumps(
                            {"state": "offline", "reason": "connection_lost"}
                        ),
                        qos=1,
                        retain=True,
                    ),
                ) as client:
                    self._client = client
                    self._connection_status = "connected"
                    self._last_connect_time = datetime.now(tz=timezone.utc)
                    reconnect_delay = _RECONNECT_MIN_DELAY
                    self._log_event("success", f"Connected to {self._broker}:{self._port}")
                    async_dispatcher_send(self.hass, SIGNAL_CONFIG_UPDATED)
                    _LOGGER.info(
                        "Connected to MQTT broker %s:%s for house '%s'",
                        self._broker, self._port, self._house_id,
                    )

                    await self._subscribe_topics(client)
                    await self._publish_availability(client, "online")
                    await self._publish_all_current_states(client)

                    async for message in client.messages:
                        await self._handle_message(message)

            except aiomqtt.MqttError as err:
                self._client = None
                if self._stopping:
                    break
                self._last_disconnect_time = datetime.now(tz=timezone.utc)
                self._reconnect_count += 1
                self._connection_status = "reconnecting"
                self._log_event(
                    "warning",
                    f"Connection lost: {err}. Reconnecting in {reconnect_delay}s (attempt {self._reconnect_count})…",
                )
                async_dispatcher_send(self.hass, SIGNAL_CONFIG_UPDATED)
                _LOGGER.warning(
                    "MQTT connection lost for house '%s': %s. Reconnecting in %ds…",
                    self._house_id, err, reconnect_delay,
                )
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * _RECONNECT_BACKOFF_FACTOR, _RECONNECT_MAX_DELAY)

            except asyncio.CancelledError:
                self._client = None
                break

            except Exception:  # noqa: BLE001
                self._client = None
                if self._stopping:
                    break
                self._last_disconnect_time = datetime.now(tz=timezone.utc)
                self._reconnect_count += 1
                self._connection_status = "reconnecting"
                self._log_event(
                    "error",
                    f"Unexpected error. Reconnecting in {reconnect_delay}s (attempt {self._reconnect_count})…",
                )
                async_dispatcher_send(self.hass, SIGNAL_CONFIG_UPDATED)
                _LOGGER.exception(
                    "Unexpected error in MQTT connection loop for house '%s'. Reconnecting in %ds…",
                    self._house_id, reconnect_delay,
                )
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * _RECONNECT_BACKOFF_FACTOR, _RECONNECT_MAX_DELAY)

        self._connection_status = "disconnected"
        self._log_event("info", "Bridge stopped")

    async def _subscribe_topics(self, client: aiomqtt.Client) -> None:
        """Subscribe to all incoming MQTT topics."""
        # Commands from app: house/{id}/command/#
        command_topic = f"house/{self._house_id}/command/#"
        await client.subscribe(command_topic, qos=2)
        _LOGGER.debug("Subscribed to %s", command_topic)

        # Heartbeat ping: house/{id}/app/command/heartbeat
        heartbeat_topic = f"house/{self._house_id}/app/command/heartbeat"
        await client.subscribe(heartbeat_topic, qos=0)
        _LOGGER.debug("Subscribed to %s", heartbeat_topic)

        # App reload request: house/{id}/app/command/reload
        reload_topic = f"house/{self._house_id}/app/command/reload"
        await client.subscribe(reload_topic, qos=1)
        _LOGGER.debug("Subscribed to %s", reload_topic)

        # Remote exposure config (retained; cloud mode only)
        if self.exposure_callback is not None:
            config_topic = f"house/{self._house_id}/config/exposure"
            await client.subscribe(config_topic, qos=1)
            _LOGGER.debug("Subscribed to %s", config_topic)

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

            old_state = event.data.get("old_state")

            if self._client is not None:
                self.hass.async_create_task(
                    self._publish_state(self._client, new_state, old_state=old_state),
                    f"turzi_publish_{entity_id}",
                )

        # Listen to ALL state changes (filtered in the callback)
        self._unsub_state_listener = self.hass.bus.async_listen(
            "state_changed", _on_state_changed
        )

    async def _publish_state(
        self, client: aiomqtt.Client, state: State, old_state: State | None = None
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
            "origin": self._build_origin(state),
        }

        # Extract domain-specific attributes
        attributes = self._extract_attributes(domain, state)

        # Climate fallback: target_temperature can be absent from new_state during
        # HVAC mode transitions (e.g. heat → cool). Mirror the original Node-RED logic:
        # 1. try old_state.temperature (HA attr name)
        # 2. try new_state.prev_target_temp
        # Always written to payload as 'target_temperature' (Turzi Protocol name).
        if domain == "climate" and (attributes or {}).get("target_temperature") is None:
            fallback: Any = None
            if old_state is not None:
                fallback = old_state.attributes.get("temperature")
            if fallback is None:
                fallback = state.attributes.get("prev_target_temp")
            if fallback is not None:
                if attributes is None:
                    attributes = {}
                attributes["target_temperature"] = fallback

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

        # Remote exposure config (PROTOCOL.md, Exposure Configuration)
        if topic == f"house/{self._house_id}/config/exposure":
            if self.exposure_callback is None:
                return
            try:
                exposure = json.loads(message.payload)
            except (json.JSONDecodeError, TypeError):
                _LOGGER.error("Invalid JSON on config/exposure")
                return
            await self.exposure_callback(exposure)
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
        command_id = payload.get("command_id")
        if command_id is not None and not isinstance(command_id, str):
            command_id = None

        # v1.1 §2 — dedupe: a repeated command_id is a duplicate delivery,
        # execute at most once (silently: the original delivery already acked).
        if command_id and self._is_duplicate_command(command_id):
            _LOGGER.debug("Ignoring duplicate command %s for %s", command_id, entity_id)
            return

        # v1.1 §2 — expiry: a late command no longer represents the actor's intent.
        if self._is_expired(payload):
            _LOGGER.warning(
                "Discarded expired command for %s (issued_at=%s)",
                entity_id, payload.get("issued_at"),
            )
            self._log_event("warning", f"Discarded expired command for {entity_id}")
            if command_id:
                await self._publish_ack(command_id, "failed", "expired")
            return

        # Guard: reject commands for entities that are not exposed.
        # This prevents the app from controlling entities the user has not
        # explicitly opted in to expose via the panel.
        if not self.should_expose(entity_id):
            _LOGGER.warning(
                "Rejected command for non-exposed entity '%s' (topic: %s)",
                entity_id,
                topic,
            )
            self._log_event(
                "warning",
                f"Rejected command for non-exposed entity: {entity_id}",
            )
            if command_id:
                await self._publish_ack(command_id, "failed", "entity_not_exposed")
            return

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
            if command_id:
                await self._publish_ack(command_id, "failed", "unsupported_command")
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

        # v1.1 §4 — call with a tracked HA context so the resulting state change
        # is attributed origin.type="turzi" with this command_id.
        service_context = Context()
        if command_id:
            self._remember_command_context(service_context, command_id)

        # Call the HA service
        try:
            await self.hass.services.async_call(
                service_domain,
                service_action,
                service_data,
                blocking=False,
                context=service_context,
            )
            self._log_event(
                "info",
                f"Command {service_domain}.{service_action} → {entity_id} (by {user_name})",
            )
            _LOGGER.info(
                "Executed command %s.%s for %s (by %s <%s>)",
                service_domain, service_action, entity_id, user_name, user_email,
            )
            if command_id:
                await self._publish_ack(command_id, "executed")
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "Failed to execute command %s.%s for %s",
                service_domain,
                service_action,
                entity_id,
            )
            if command_id:
                await self._publish_ack(command_id, "failed", "platform_error")

    # -------------------------------------------------------------------------
    # Availability & command acks (Protocol v1.1)
    # -------------------------------------------------------------------------

    async def _publish_availability(self, client: aiomqtt.Client, state: str) -> None:
        """Publish the retained availability payload (v1.1 §1).

        config_revision doubles as the exposure-config acknowledgment (§5).
        """
        payload: dict[str, Any] = {
            "state": state,
            "timestamp": math.floor(datetime.now(tz=timezone.utc).timestamp()),
            "protocol_version": PROTOCOL_VERSION,
        }
        if self.config_revision is not None:
            payload["config_revision"] = self.config_revision
        try:
            await client.publish(
                f"house/{self._house_id}/availability",
                payload=json.dumps(payload),
                qos=1,
                retain=True,
            )
        except aiomqtt.MqttError:
            _LOGGER.warning("Failed to publish availability for house '%s'", self._house_id)

    async def async_set_config_revision(self, revision: int | None) -> None:
        """Update the applied exposure revision and re-announce availability."""
        if revision == self.config_revision:
            return
        self.config_revision = revision
        if self._client is not None:
            await self._publish_availability(self._client, "online")

    async def _publish_ack(
        self, command_id: str, status: str, reason: str | None = None
    ) -> None:
        """Publish a command acknowledgment (v1.1 §3). No-op without a client."""
        if self._client is None:
            return
        payload = {
            "command_id": command_id,
            "status": status,
            "reason": reason,
            "timestamp": math.floor(datetime.now(tz=timezone.utc).timestamp()),
        }
        try:
            await self._client.publish(
                f"house/{self._house_id}/ack/{command_id}",
                payload=json.dumps(payload),
                qos=1,
                retain=False,
            )
        except aiomqtt.MqttError:
            _LOGGER.warning("Failed to publish ack for command %s", command_id)

    def _is_duplicate_command(self, command_id: str) -> bool:
        """Dedupe check with retention >= the TTL ceiling (v1.1 §2)."""
        now = asyncio.get_running_loop().time()
        cutoff = now - DEFAULT_TTL_CEILING_SECONDS
        self._seen_command_ids = {
            cid: t for cid, t in self._seen_command_ids.items() if t > cutoff
        }
        if command_id in self._seen_command_ids:
            return True
        self._seen_command_ids[command_id] = now
        return False

    @staticmethod
    def _is_expired(payload: dict) -> bool:
        """Command expiry check (v1.1 §2): issued_at + clamped TTL, with skew tolerance."""
        issued_at = payload.get("issued_at")
        if not isinstance(issued_at, (int, float)):
            return False  # v1.0 command — no expiry check
        ttl = payload.get("ttl_seconds")
        if not isinstance(ttl, (int, float)) or ttl <= 0:
            ttl = DEFAULT_TTL_CEILING_SECONDS
        effective_ttl = min(ttl, DEFAULT_TTL_CEILING_SECONDS)
        now = datetime.now(tz=timezone.utc).timestamp()
        return now > issued_at + effective_ttl + CLOCK_SKEW_TOLERANCE_SECONDS

    def _remember_command_context(self, ctx: Context, command_id: str) -> None:
        """Map an HA context to a command_id for origin attribution (v1.1 §4)."""
        if len(self._command_contexts) > 256:
            # Drop the oldest half (dicts preserve insertion order)
            for key in list(self._command_contexts)[:128]:
                del self._command_contexts[key]
        self._command_contexts[ctx.id] = command_id

    def _build_origin(self, state: State) -> dict[str, Any]:
        """Classify what caused a state change from its HA context (v1.1 §4)."""
        ctx = state.context
        if ctx is None:
            return {"type": "unknown"}
        command_id = self._command_contexts.get(ctx.id) or (
            self._command_contexts.get(ctx.parent_id) if ctx.parent_id else None
        )
        if command_id is not None:
            return {"type": "turzi", "command_id": command_id}
        if ctx.parent_id is not None:
            return {"type": "automation"}
        if ctx.user_id is not None:
            return {"type": "core_user"}
        return {"type": "physical"}

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
                qos=0,
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
