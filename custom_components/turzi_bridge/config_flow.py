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
    ConfigSubentryData,
    ConfigSubentryFlow,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_API_BASE_URL,
    CONF_AUTO_ADD_NEW,
    CONF_BRIDGE_TOKEN,
    CONF_BROKER,
    CONF_ENROLLMENT_TOKEN,
    CONF_FILTER_SNAPSHOT,
    CONF_HOUSE_ID,
    CONF_MODE,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USE_TLS,
    CONF_USERNAME,
    DEFAULT_AUTO_ADD_NEW,
    DEFAULT_CLOUD_API_BASE_URL,
    DEFAULT_FILTERS,
    DEFAULT_PORT,
    DOMAIN,
    FILTER_DEVICE_CLASSES,
    FILTER_DOMAIN,
    SUBENTRY_DOMAIN_FILTER,
    SUBENTRY_ENTITY_FILTER,
    SUBENTRY_EXCLUSION,
)
from .enrollment import EnrollmentError, async_enroll
from .scope import blocked_of, count_published, domain_filter_title, filters_of, take_snapshot
from .subentry_flows import DomainFilterFlow, EntityFilterFlow, ExclusionFlow

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


async def _initial_subentries(hass: HomeAssistant) -> list[ConfigSubentryData]:
    """The preloaded domain filters, as the rows a new bridge starts with."""
    return [
        ConfigSubentryData(
            data=dict(item),
            subentry_type=SUBENTRY_DOMAIN_FILTER,
            title=await domain_filter_title(hass, item[FILTER_DOMAIN], item[FILTER_DEVICE_CLASSES]),
            unique_id=item[FILTER_DOMAIN],
        )
        for item in DEFAULT_FILTERS
    ]


def _settings_schema(auto_add_new: bool) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_AUTO_ADD_NEW, default=auto_add_new): BooleanSelector()})


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
    # 3: what is published lives in subentries (domain filters, entity
    # filters, exclusions), one row each on the bridge's page.
    VERSION = 3
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Connection details held until the last step creates the entry."""
        self._data: dict[str, Any] = {}
        self._title = ""

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """The bridge page's three add buttons, one per kind of row."""
        return {
            SUBENTRY_DOMAIN_FILTER: DomainFilterFlow,
            SUBENTRY_ENTITY_FILTER: EntityFilterFlow,
            SUBENTRY_EXCLUSION: ExclusionFlow,
        }

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
                self._data = datos
                self._title = f"turzi Bridge for Home Assistant — {result.house_id}"
                return await self.async_step_settings()

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
                self._data = {**user_input, CONF_MODE: "manual"}
                self._title = f"turzi Bridge for Home Assistant — {user_input[CONF_HOUSE_ID]}"
                return await self.async_step_settings()

        return self.async_show_form(
            step_id="manual",
            data_schema=_build_broker_schema(),
            errors=errors,
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Last step: the options, then the bridge with its preloaded filters.

        The filters and exclusions themselves are rows on the bridge's page
        from here on (`subentry_flows.py`); setup only creates the defaults.
        """
        if user_input is not None:
            return self.async_create_entry(
                title=self._title,
                data=self._data,
                options={
                    CONF_AUTO_ADD_NEW: user_input[CONF_AUTO_ADD_NEW],
                    CONF_FILTER_SNAPSHOT: take_snapshot(self.hass, DEFAULT_FILTERS),
                },
                subentries=await _initial_subentries(self.hass),
            )

        published, _ = count_published(self.hass, DEFAULT_FILTERS, set())
        return self.async_show_form(
            step_id="settings",
            data_schema=_settings_schema(DEFAULT_AUTO_ADD_NEW),
            description_placeholders={
                "filters": str(len(DEFAULT_FILTERS)),
                "published": str(published),
            },
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
    """Configure (the gear on the bridge's row): «Opciones».

    Filters and exclusions are not here: they are rows on the bridge's page,
    each with its own edit and delete. This step holds what applies to all of
    them.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Automatic exposure, with what the rows publish today."""
        entry = self.config_entry
        if user_input is not None:
            # Merge, never replace. `async_create_entry` in an options flow is
            # a FULL overwrite (`OptionsFlowManager.async_finish_flow` calls
            # `async_update_entry(entry, options=result["data"])`), so a
            # literal dict here would delete every key this form does not
            # draw. Today that is `config_revision`, the last exposure revision
            # applied from the platform (PROTOCOL.md §5); with it gone,
            # `cloud.async_apply_exposure` would re-apply the platform's
            # exposure over this edit about ten seconds later.
            #
            # The snapshot is retaken on every save: with automatic exposure
            # off, saving is what lets the entities that appeared since in.
            return self.async_create_entry(
                data={
                    **entry.options,
                    CONF_AUTO_ADD_NEW: user_input[CONF_AUTO_ADD_NEW],
                    CONF_FILTER_SNAPSHOT: take_snapshot(self.hass, filters_of(entry)),
                }
            )

        published, held = count_published(self.hass, filters_of(entry), blocked_of(entry))
        return self.async_show_form(
            step_id="init",
            data_schema=_settings_schema(entry.options.get(CONF_AUTO_ADD_NEW, DEFAULT_AUTO_ADD_NEW)),
            description_placeholders={"published": str(published), "held": str(held)},
        )
