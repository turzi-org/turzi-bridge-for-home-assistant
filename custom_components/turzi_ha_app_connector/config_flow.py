"""Config flow and Options flow for the Turzi App Connector integration."""

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
from homeassistant.helpers import selector

from .const import (
    CONF_ADDITIONAL_ENTITIES,
    CONF_BROKER,
    CONF_EXCLUDED_ENTITIES,
    CONF_EXPOSE_LABEL,
    CONF_HOUSE_ID,
    CONF_INCLUDED_DOMAINS,
    CONF_LABEL_MODE,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USE_TLS,
    CONF_USERNAME,
    DEFAULT_EXPOSE_LABEL,
    DEFAULT_INCLUDED_DOMAINS,
    DEFAULT_LABEL_MODE,
    DEFAULT_PORT,
    DOMAIN,
    LabelMode,
    SELECTABLE_DOMAINS,
)

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
        tls_params = ssl.create_default_context() if use_tls else None
        async with aiomqtt.Client(
            hostname=broker,
            port=port,
            username=username or None,
            password=password or None,
            tls_params=tls_params,
            timeout=10,
        ):
            pass
        return True
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Failed to connect to MQTT broker %s:%s", broker, port)
        return False


def _build_broker_schema(
    defaults: dict[str, Any] | None = None,
) -> vol.Schema:
    """Build the broker configuration schema with optional defaults."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_BROKER, default=defaults.get(CONF_BROKER, "")
            ): str,
            vol.Required(
                CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)
            ): int,
            vol.Optional(
                CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")
            ): str,
            vol.Optional(
                CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")
            ): str,
            vol.Required(
                CONF_HOUSE_ID, default=defaults.get(CONF_HOUSE_ID, "")
            ): str,
            vol.Required(
                CONF_USE_TLS, default=defaults.get(CONF_USE_TLS, False)
            ): bool,
        }
    )


class TurziAppConnectorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Turzi App Connector."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate house_id uniqueness
            await self.async_set_unique_id(user_input[CONF_HOUSE_ID])
            self._abort_if_unique_id_configured()

            # Validate broker hostname
            broker = user_input[CONF_BROKER].strip()
            if not broker:
                errors["base"] = "invalid_host"
            else:
                user_input[CONF_BROKER] = broker

                # Test MQTT connection
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
                title = f"Turzi - {user_input[CONF_HOUSE_ID]}"
                return self.async_create_entry(
                    title=title,
                    data=user_input,
                    options={
                        CONF_EXPOSE_LABEL: DEFAULT_EXPOSE_LABEL,
                        CONF_LABEL_MODE: DEFAULT_LABEL_MODE,
                        CONF_INCLUDED_DOMAINS: DEFAULT_INCLUDED_DOMAINS,
                        CONF_ADDITIONAL_ENTITIES: [],
                        CONF_EXCLUDED_ENTITIES: [],
                    },
                )

        return self.async_show_form(
            step_id="user",
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
                    title=f"Turzi - {user_input[CONF_HOUSE_ID]}",
                    data_updates=user_input,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_build_broker_schema(defaults=dict(entry.data)),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> TurziOptionsFlow:
        """Get the options flow handler."""
        return TurziOptionsFlow(config_entry)


class TurziOptionsFlow(OptionsFlow):
    """Handle the options flow for entity selection."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry
        self._expose_label: str = ""
        self._label_mode: str = DEFAULT_LABEL_MODE
        self._included_domains: list[str] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Label and domain selection."""
        if user_input is not None:
            self._expose_label = user_input.get(CONF_EXPOSE_LABEL, "").strip().lower()
            self._label_mode = user_input.get(CONF_LABEL_MODE, DEFAULT_LABEL_MODE)
            self._included_domains = user_input.get(CONF_INCLUDED_DOMAINS, [])
            return await self.async_step_entities()

        domain_options = [
            selector.SelectOptionDict(value=domain, label=domain)
            for domain in SELECTABLE_DOMAINS
        ]
        current_label = self._config_entry.options.get(
            CONF_EXPOSE_LABEL, DEFAULT_EXPOSE_LABEL
        )
        current_mode = self._config_entry.options.get(
            CONF_LABEL_MODE, DEFAULT_LABEL_MODE
        )
        current_domains = self._config_entry.options.get(
            CONF_INCLUDED_DOMAINS, DEFAULT_INCLUDED_DOMAINS
        )

        mode_options = [
            selector.SelectOptionDict(
                value=LabelMode.SEED,
                label="Seed (one-time): label matching entities now, then manage manually",
            ),
            selector.SelectOptionDict(
                value=LabelMode.AUTOMATIC,
                label="Automatic: labels kept in sync with domain rules at all times",
            ),
            selector.SelectOptionDict(
                value=LabelMode.MIXED,
                label="Mixed: automatic domain sync + manual additions protected",
            ),
        ]

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LABEL_MODE,
                        default=current_mode,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=mode_options,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Optional(
                        CONF_EXPOSE_LABEL,
                        default=current_label,
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT,
                        )
                    ),
                    vol.Optional(
                        CONF_INCLUDED_DOMAINS,
                        default=current_domains,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=domain_options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: Fine-tune individual entities (include/exclude)."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_EXPOSE_LABEL: self._expose_label,
                    CONF_LABEL_MODE: self._label_mode,
                    CONF_INCLUDED_DOMAINS: self._included_domains,
                    CONF_ADDITIONAL_ENTITIES: user_input.get(
                        CONF_ADDITIONAL_ENTITIES, []
                    ),
                    CONF_EXCLUDED_ENTITIES: user_input.get(
                        CONF_EXCLUDED_ENTITIES, []
                    ),
                }
            )

        current_additional = self._config_entry.options.get(
            CONF_ADDITIONAL_ENTITIES, []
        )
        current_excluded = self._config_entry.options.get(
            CONF_EXCLUDED_ENTITIES, []
        )

        return self.async_show_form(
            step_id="entities",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_ADDITIONAL_ENTITIES,
                        default=current_additional,
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                    vol.Optional(
                        CONF_EXCLUDED_ENTITIES,
                        default=current_excluded,
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                }
            ),
        )
