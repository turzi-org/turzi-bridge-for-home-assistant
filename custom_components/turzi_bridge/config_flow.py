"""Config flow for the turzi Bridge integration."""

from __future__ import annotations

import logging
import ssl
from typing import Any

import aiomqtt
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    NOISY_DOMAINS,
    SELECTABLE_DOMAINS,
    CONF_API_BASE_URL,
    CONF_AUTO_ADD_NEW,
    CONF_BRIDGE_TOKEN,
    CONF_BROKER,
    CONF_ENROLLMENT_TOKEN,
    CONF_EXPOSED_ENTITIES,
    CONF_HOUSE_ID,
    CONF_INCLUDED_DOMAINS,
    CONF_MODE,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USE_TLS,
    CONF_USERNAME,
    DEFAULT_AUTO_ADD_NEW,
    CONF_NEVER_EXPOSE,
    DEFAULT_CLOUD_API_BASE_URL,
    DEFAULT_INCLUDED_DOMAINS,
    DEFAULT_PORT,
    DOMAIN,
)
from .enrollment import EnrollmentError, async_enroll

_LOGGER = logging.getLogger(__name__)


async def _test_mqtt_connection(
    broker: str,
    port: int,
    username: str | None,
    password: str | None,
    use_tls: bool,
) -> bool:
    """Test the MQTT broker connection."""
    try:
        # `tls_context`, no `tls_params` — ver la nota larga en
        # `mqtt_bridge._connection_loop`. Acá el efecto era peor: el except de
        # abajo se traga TODO, así que contra un broker con TLS este test
        # devolvía False y la pantalla decía "no se pudo conectar" cuando lo que
        # había fallado era nuestro propio argumento.
        tls_context = ssl.create_default_context() if use_tls else None
        async with aiomqtt.Client(
            hostname=broker,
            port=port,
            username=username or None,
            password=password or None,
            tls_context=tls_context,
            timeout=10,
        ):
            pass
        return True
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Failed to connect to MQTT broker %s:%s", broker, port)
        return False


def _build_broker_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the broker configuration schema with optional defaults."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_BROKER, default=defaults.get(CONF_BROKER, "")): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Optional(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Optional(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
            vol.Required(CONF_HOUSE_ID, default=defaults.get(CONF_HOUSE_ID, "")): str,
            vol.Required(CONF_USE_TLS, default=defaults.get(CONF_USE_TLS, False)): bool,
        }
    )


def _default_options(hass, cloud: bool = False) -> dict[str, Any]:
    """Default exposure options.

    Included domains expose wholesale; exposed_entities holds MANUAL
    additions only (empty by default). Cloud mode includes everything
    selectable except the noisy domains (NOISY_DOMAINS); individual
    noisy-domain entities are added manually when needed.
    """
    included = (
        [d for d in SELECTABLE_DOMAINS if d not in NOISY_DOMAINS]
        if cloud
        else DEFAULT_INCLUDED_DOMAINS
    )
    return {
        CONF_INCLUDED_DOMAINS: included,
        CONF_EXPOSED_ENTITIES: [],
        CONF_AUTO_ADD_NEW: True if cloud else DEFAULT_AUTO_ADD_NEW,
    }


def _cloud_schema(default_base_url: str) -> vol.Schema:
    """Enrollment form: the key is short-lived and single-use — a plain
    visible text field, never password-masked."""
    return vol.Schema(
        {
            vol.Required(CONF_ENROLLMENT_TOKEN): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT, autocomplete="off")
            ),
            vol.Optional(CONF_API_BASE_URL, default=default_base_url): str,
        }
    )


class TurziAppConnectorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for turzi Bridge.

    Two setup modes (PROTOCOL.md §4 deployment modes):
    - cloud: paste a single-use enrollment token; broker connection and
      per-home credentials are provisioned by the Turzi platform.
    - manual: enter broker details directly (self-hosted / local mode).
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First step: pick the setup mode."""
        return self.async_show_menu(step_id="user", menu_options=["cloud", "manual"])

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Cloud setup: exchange an enrollment token for full provisioning."""
        errors: dict[str, str] = {}

        if user_input is not None:
            base_url = (
                user_input.get(CONF_API_BASE_URL) or DEFAULT_CLOUD_API_BASE_URL
            ).strip()
            try:
                result = await async_enroll(
                    self.hass, base_url, user_input[CONF_ENROLLMENT_TOKEN]
                )
            except EnrollmentError as err:
                errors["base"] = err.code
            else:
                await self.async_set_unique_id(result.house_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"turzi Bridge for Home Assistant — {result.house_id}",
                    data={
                        CONF_MODE: "cloud",
                        CONF_BROKER: result.mqtt_host,
                        CONF_PORT: result.mqtt_port,
                        CONF_USERNAME: result.mqtt_username,
                        CONF_PASSWORD: result.mqtt_password,
                        CONF_HOUSE_ID: result.house_id,
                        CONF_USE_TLS: result.mqtt_tls,
                        CONF_BRIDGE_TOKEN: result.bridge_token,
                        CONF_API_BASE_URL: base_url,
                    },
                    options=_default_options(self.hass, cloud=True),
                )

        return self.async_show_form(
            step_id="cloud",
            data_schema=_cloud_schema(DEFAULT_CLOUD_API_BASE_URL),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Platform unlinked us (or the token was revoked): reconnect."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter a new enrollment key — options (domains, entities,
        blocklist) are preserved; only the connection is re-provisioned."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            base_url = (
                user_input.get(CONF_API_BASE_URL)
                or entry.data.get(CONF_API_BASE_URL)
                or DEFAULT_CLOUD_API_BASE_URL
            ).strip()
            try:
                result = await async_enroll(
                    self.hass, base_url, user_input[CONF_ENROLLMENT_TOKEN]
                )
            except EnrollmentError as err:
                errors["base"] = err.code
            else:
                if entry.unique_id != result.house_id:
                    self.hass.config_entries.async_update_entry(
                        entry, unique_id=result.house_id
                    )
                return self.async_update_reload_and_abort(
                    entry,
                    title=f"turzi Bridge for Home Assistant — {result.house_id}",
                    data={
                        CONF_MODE: "cloud",
                        CONF_BROKER: result.mqtt_host,
                        CONF_PORT: result.mqtt_port,
                        CONF_USERNAME: result.mqtt_username,
                        CONF_PASSWORD: result.mqtt_password,
                        CONF_HOUSE_ID: result.house_id,
                        CONF_USE_TLS: result.mqtt_tls,
                        CONF_BRIDGE_TOKEN: result.bridge_token,
                        CONF_API_BASE_URL: base_url,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_cloud_schema(
                entry.data.get(CONF_API_BASE_URL, DEFAULT_CLOUD_API_BASE_URL)
            ),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual setup (self-hosted / local mode)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOUSE_ID])
            self._abort_if_unique_id_configured()

            broker = user_input[CONF_BROKER].strip()
            if not broker:
                errors["base"] = "invalid_host"
            else:
                user_input[CONF_BROKER] = broker
                connected = await _test_mqtt_connection(
                    broker=broker,
                    port=user_input[CONF_PORT],
                    username=user_input.get(CONF_USERNAME),
                    password=user_input.get(CONF_PASSWORD),
                    use_tls=user_input[CONF_USE_TLS],
                )
                if not connected:
                    errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(
                    title=f"turzi Bridge for Home Assistant — {user_input[CONF_HOUSE_ID]}",
                    data={**user_input, CONF_MODE: "manual"},
                    options=_default_options(self.hass),
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=_build_broker_schema(),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the broker settings."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            broker = user_input[CONF_BROKER].strip()
            if not broker:
                errors["base"] = "invalid_host"
            else:
                user_input[CONF_BROKER] = broker
                connected = await _test_mqtt_connection(
                    broker=broker,
                    port=user_input[CONF_PORT],
                    username=user_input.get(CONF_USERNAME),
                    password=user_input.get(CONF_PASSWORD),
                    use_tls=user_input[CONF_USE_TLS],
                )
                if not connected:
                    errors["base"] = "cannot_connect"

            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    title=f"turzi Bridge for Home Assistant — {user_input[CONF_HOUSE_ID]}",
                    data_updates=user_input,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_build_broker_schema(defaults=dict(entry.data)),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TurziOptionsFlow:
        """Create the options flow."""
        return TurziOptionsFlow()


class TurziOptionsFlow(OptionsFlow):
    """Options: exposure management and the privacy blocklist.

    Replaces the removed sidebar panel. The privacy blocklist applies in
    every mode and cannot be overridden remotely (PROTOCOL.md, Exposure
    Configuration): entities listed there are never published, even if a
    future platform exposure revision includes them.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage exposure and privacy options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_INCLUDED_DOMAINS: user_input.get(
                        CONF_INCLUDED_DOMAINS, DEFAULT_INCLUDED_DOMAINS
                    ),
                    CONF_EXPOSED_ENTITIES: user_input.get(CONF_EXPOSED_ENTITIES, []),
                    CONF_AUTO_ADD_NEW: user_input.get(
                        CONF_AUTO_ADD_NEW, DEFAULT_AUTO_ADD_NEW
                    ),
                    CONF_NEVER_EXPOSE: user_input.get(CONF_NEVER_EXPOSE, []),
                }
            )

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_INCLUDED_DOMAINS,
                    default=options.get(
                        CONF_INCLUDED_DOMAINS, DEFAULT_INCLUDED_DOMAINS
                    ),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=SELECTABLE_DOMAINS,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_EXPOSED_ENTITIES,
                    default=options.get(CONF_EXPOSED_ENTITIES, []),
                ): EntitySelector(EntitySelectorConfig(multiple=True)),
                vol.Required(
                    CONF_AUTO_ADD_NEW,
                    default=options.get(CONF_AUTO_ADD_NEW, DEFAULT_AUTO_ADD_NEW),
                ): BooleanSelector(),
                vol.Required(
                    CONF_NEVER_EXPOSE,
                    default=options.get(CONF_NEVER_EXPOSE, []),
                ): EntitySelector(EntitySelectorConfig(multiple=True)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
