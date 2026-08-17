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


def _build_broker_schema(
    defaults: dict[str, Any] | None = None, include_house_id: bool = True
) -> vol.Schema:
    """Build the broker configuration schema with optional defaults.

    `include_house_id=False` on reconfigure — see the note at that call site.
    """
    defaults = defaults or {}
    fields: dict[Any, Any] = {
        vol.Required(CONF_BROKER, default=defaults.get(CONF_BROKER, "")): str,
        vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
        vol.Optional(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
        vol.Optional(
            CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")
        ): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="off")
        ),
    }
    if include_house_id:
        house_id = vol.Required(CONF_HOUSE_ID, default=defaults.get(CONF_HOUSE_ID, ""))
        fields[house_id] = str
    fields[vol.Required(CONF_USE_TLS, default=defaults.get(CONF_USE_TLS, False))] = bool
    return vol.Schema(fields)


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

    # 2: `included_domains` changed meaning. Under v1 it only filtered which
    # NEW entities auto-add was allowed to append to `exposed_entities`, and
    # `should_expose` was pure set membership against that list. Now a listed
    # domain is exposed wholesale. Same key, opposite blast radius — see
    # `async_migrate_entry` in __init__.py.
    VERSION = 2

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
                datos = {
                    CONF_MODE: "cloud",
                    CONF_BROKER: result.mqtt_host,
                    CONF_PORT: result.mqtt_port,
                    CONF_USERNAME: result.mqtt_username,
                    CONF_PASSWORD: result.mqtt_password,
                    CONF_HOUSE_ID: result.house_id,
                    CONF_USE_TLS: result.mqtt_tls,
                    CONF_BRIDGE_TOKEN: result.bridge_token,
                    CONF_API_BASE_URL: base_url,
                }
                await self.async_set_unique_id(result.house_id)

                # `updates=` NO es un detalle: enrolar ya fue DESTRUCTIVO del
                # lado del servidor cuando llegamos acá. `enroll` revoca la fila
                # del bridge anterior y vuelve a acuñar la contraseña MQTT, así
                # que para cuando sabemos que esta casa ya tenía una entrada, la
                # instalación que había quedó muerta: su token no vale y su
                # contraseña ya no existe en el broker.
                #
                # Abortar sin más —lo que hacía antes— dejaba esa entrada con
                # credenciales viejas y sin forma de recuperarse salvo borrarla
                # y volver a enrolar con OTRA llave, porque la primera ya se
                # consumió. O sea: reintentar un enrolamiento sobre una casa que
                # ya andaba la rompía.
                #
                # No se puede chequear antes: `house_id` sale de la respuesta.
                # Así que se adopta lo recién acuñado en la entrada existente y
                # se recarga, que es lo que el servidor ya dio por hecho.
                self._abort_if_unique_id_configured(
                    updates=datos, reload_on_update=True
                )
                return self.async_create_entry(
                    title=f"turzi Bridge for Home Assistant — {result.house_id}",
                    data=datos,
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
        return await self._async_enroll_step(
            "reauth_confirm",
            self._get_reauth_entry(),
            user_input,
            success_reason="reauth_successful",
        )

    async def _async_enroll_step(
        self,
        step_id: str,
        entry: ConfigEntry,
        user_input: dict[str, Any] | None,
        success_reason: str,
    ) -> ConfigFlowResult:
        """Re-enrollment body shared by reauth and cloud reconfigure.

        `data=` replaces instead of merging: a re-provisioned entry must not
        keep the previous `bridge_token` or `api_base_url`. `options` is not
        passed at all, so exposure, the privacy blocklist and
        `config_revision` survive untouched.
        """
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
                    # The key enrolled a DIFFERENT house than this entry holds.
                    # Repointing onto a house another entry already owns leaves
                    # two entries on `house/{id}/…`: both answer every command,
                    # both publish state, and each one's retained reconciliation
                    # clears the other's topics. Nothing has been written yet at
                    # this point, and nothing may be — an abort has to leave the
                    # entry exactly as it was.
                    if any(
                        other.entry_id != entry.entry_id
                        and other.unique_id == result.house_id
                        for other in self._async_current_entries(include_ignore=False)
                    ):
                        return self.async_abort(reason="house_already_configured")
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
                    reason=success_reason,
                )

        return self.async_show_form(
            step_id=step_id,
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

        # Reconfigure is offered per integration, not per mode, so a cloud
        # entry lands on this form too — and it MERGES: `mode`,
        # `bridge_token` and `api_base_url` are not in the form, so they
        # survive verbatim next to hand-typed broker fields. The result is a
        # cloud entry pointing at a broker nobody provisioned that still POSTs
        # its catalog with the old token, re-raising `token_revoked` on every
        # 401. And the `unlinked` repair sends the installer here by name.
        # Cloud entries re-provision; their connection is never edited by hand.
        if entry.data.get(CONF_MODE) == "cloud":
            return await self.async_step_reconfigure_cloud()

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
                    title=f"turzi Bridge for Home Assistant — {entry.data[CONF_HOUSE_ID]}",
                    data_updates=user_input,
                )

        return self.async_show_form(
            step_id="reconfigure",
            # No house_id field. It is the MQTT topic prefix — `house/{id}/
            # state/…`, `house/{id}/command/#`, availability — so editing it
            # in place moves the entry to a new prefix while everything
            # already retained under the old one stays on the broker forever:
            # `_reconcile_retained_state` only ever reaches the CURRENT
            # prefix, so the stale state topics and the retained `online`
            # availability outlive every client that could clear them. The
            # entry's unique_id would go stale too, freeing a second entry for
            # the same house. A different house is a new entry, not an edit.
            data_schema=_build_broker_schema(
                defaults=dict(entry.data), include_house_id=False
            ),
            errors=errors,
        )

    async def async_step_reconfigure_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Cloud entries reconfigure by re-provisioning: the enrollment form
        reauth uses, reached from Reconfigure instead of from an unlink."""
        return await self._async_enroll_step(
            "reconfigure_cloud",
            self._get_reconfigure_entry(),
            user_input,
            success_reason="reconfigure_successful",
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
            # Merge, never replace. `async_create_entry` in an options flow is
            # a FULL overwrite —  HA's `OptionsFlowManager.async_finish_flow`
            # calls `async_update_entry(entry, options=result["data"])` — so a
            # literal dict here silently deletes every key this form does not
            # draw. Today that is `config_revision`, the last exposure revision
            # applied from the platform (PROTOCOL.md §5).
            #
            # Losing it is not cosmetic: it re-arms the replay this bridge just
            # acked. `cloud.async_apply_exposure` skips a revision when
            # `revision <= (options.get(CONF_CONFIG_REVISION) or 0)`; with the
            # key gone that reads `revision <= 0`, false for every real
            # revision, so the next catalog round-trip re-applies the
            # platform's exposure over the edit that was just saved — about ten
            # seconds after the installer saved it, with no error anywhere.
            return self.async_create_entry(
                data={
                    **self.config_entry.options,
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
