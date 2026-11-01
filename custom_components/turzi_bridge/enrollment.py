"""Turzi Bridge Cloud API client — enrollment (BRIDGE_CLOUD_API.md).

Exchanges a single-use enrollment token for everything the bridge needs:
house_id, a long-lived bridge token, and a per-home MQTT credential.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import (
    CONF_API_ADDRESS,
    CONF_API_BASE_URL,
    CONF_BROKER,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_TLS_SERVER_NAME,
    CONF_USE_TLS,
    CONF_USERNAME,
    DOMAIN,
    PROTOCOL_VERSION,
)
from .tls import async_post, async_request

_LOGGER = logging.getLogger(__name__)

ENROLL_TIMEOUT = aiohttp.ClientTimeout(total=15)


class EnrollmentError(Exception):
    """Enrollment failed; `code` is a stable error identifier for the UI."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class EnrollResult:
    house_id: str
    bridge_token: str
    mqtt_host: str
    mqtt_port: int
    mqtt_tls: bool
    mqtt_username: str
    mqtt_password: str
    # With a Turzi Stack in the building: the name the broker's certificate is
    # for, and how the API is reached through it from now on. None otherwise.
    mqtt_tls_server_name: str | None = None
    api_base_url: str | None = None
    api_address: str | None = None
    # The entry's title from the community's and organization's names, or None
    # where the API sends none (an older platform): the title stays as it is.
    title: str | None = None


def entry_title(names: Any) -> str | None:
    """The config entry's title from the API's `names` (BRIDGE_CLOUD_API.md §2, #1160).

    «Turzi · Dev Smoke Test (Turzi)», or «Turzi · Dev Smoke Test» where no
    organization administers the community. None where there is no community
    name, so the entry keeps the title it has.
    """
    if not isinstance(names, dict):
        return None
    community = str(names.get("community") or "").strip()
    if not community:
        return None
    organization = str(names.get("organization") or "").strip()
    return f"Turzi · {community} ({organization})" if organization else f"Turzi · {community}"


async def async_enroll(
    hass: HomeAssistant, base_url: str, enrollment_token: str, api_address: str | None = None
) -> EnrollResult:
    """Call POST {base_url}/bridge/enroll and return the provisioned config.

    `api_address` is where to dial when `base_url` names a Turzi Stack (tls.py).
    """
    integration = await async_get_integration(hass, DOMAIN)
    payload = {
        "enrollment_token": enrollment_token.strip(),
        "bridge": {
            "type": "home-assistant",
            "bridge_version": integration.version and str(integration.version),
            "core_version": HA_VERSION,
            "protocol_version": PROTOCOL_VERSION,
        },
    }

    url = f"{base_url.rstrip('/')}/bridge/enroll"
    try:
        async with async_post(hass, base_url, api_address, "/bridge/enroll", json=payload, timeout=ENROLL_TIMEOUT) as resp:
            # El servidor manda un código estable en el cuerpo: {"error": "..."}.
            # Se lee ANTES de decidir, porque es más específico que el status.
            server_code: str | None = None
            if resp.status != 200:
                try:
                    raw_error = (await resp.json()).get("error")
                except Exception:  # noqa: BLE001 — cuerpo vacío o no-JSON
                    raw_error = None
                if isinstance(raw_error, str):
                    server_code = raw_error
                elif raw_error is not None:
                    # Only the bridge routes answer {"error": "<code>"}; the API's
                    # generic handler nests {"error": {"code": ...}}. A dict is
                    # truthy, so it would slip through every `server_code or ...`
                    # below and land in errors["base"], where the frontend looks up
                    # config.error.[object Object] and prints a raw identifier.
                    # Those codes name internal faults (DATABASE_ERROR,
                    # INTERNAL_SERVER_ERROR) that no installer can act on anyway:
                    # they belong in the log, not in the dialog.
                    _LOGGER.error(
                        "Enrollment failed with a server fault: %s", raw_error
                    )

            if resp.status == 429:
                raise EnrollmentError("rate_limited")
            if resp.status in (404, 410):
                # Two different 404s reach here. The enroll route answers a flat
                # {"error": "token_unknown"} when the key is bad; Express answers
                # its own nested 404 when the base URL does not resolve to the API
                # at all. So no flat code on a 404 means the URL is wrong, not the
                # key — and that URL is an editable field whose default already
                # changed once (53559f1), so old installs still carry a base that
                # cannot serve /bridge/enroll. Calling it "bad key" sends the
                # installer to burn fresh single-use keys against a URL that will
                # never work. 410 only ever comes from the enroll route.
                if resp.status == 404 and server_code is None:
                    _LOGGER.error(
                        "Enrollment got HTTP 404 with no bridge error code from %s: "
                        "the API base URL does not resolve to a Turzi API",
                        url,
                    )
                    raise EnrollmentError("api_url_invalid")
                raise EnrollmentError("token_invalid")
            if resp.status == 409:
                # 409 es "la comunidad todavía no está lista", pero el motivo
                # varía: sin broker asignado, o con broker pero sin credencial
                # de dynsec cargada. Son arreglos distintos, así que se pasa el
                # código del servidor cuando viene uno.
                raise EnrollmentError(server_code or "home_not_ready")
            if resp.status != 200:
                # Antes: cualquier status no contemplado se aplanaba a
                # "cannot_connect", que dice "revisá tu red" — y mandaba a mirar
                # donde no estaba el problema. Si el servidor se explicó, se le
                # cree; el status queda en el log igual.
                _LOGGER.error(
                    "Enrollment failed with HTTP %s (server code: %s)",
                    resp.status,
                    server_code or "none",
                )
                raise EnrollmentError(server_code or "cannot_connect")
            body = await resp.json()
    except EnrollmentError:
        raise
    except (aiohttp.ClientError, TimeoutError) as err:
        _LOGGER.error("Enrollment request failed: %s", err)
        raise EnrollmentError("cannot_connect") from err

    try:
        mqtt = body["mqtt"]
        return EnrollResult(
            house_id=body["house_id"],
            bridge_token=body["bridge_token"],
            mqtt_host=mqtt["host"],
            mqtt_port=int(mqtt.get("port", 1883)),
            mqtt_tls=bool(mqtt.get("tls", False)),
            mqtt_username=mqtt["username"],
            mqtt_password=mqtt["password"],
            mqtt_tls_server_name=str(mqtt["tls_server_name"]) if mqtt.get("tls_server_name") else None,
            api_base_url=str(api["base_url"]) if (api := body.get("api") or {}).get("base_url") else None,
            api_address=str(api["address"]) if api.get("address") else None,
            title=entry_title(body.get("names")),
        )
    except (KeyError, TypeError, ValueError) as err:
        _LOGGER.error("Malformed enrollment response: %s", err)
        raise EnrollmentError("cannot_connect") from err


@dataclass
class ConnectionResult:
    """Where this bridge's broker is now, and how the API is reached, as the API says."""

    mqtt_host: str
    mqtt_port: int
    mqtt_tls: bool
    mqtt_username: str
    mqtt_password: str
    mqtt_tls_server_name: str | None = None
    api_base_url: str | None = None
    api_address: str | None = None
    title: str | None = None


async def async_fetch_connection(
    hass: HomeAssistant, base_url: str, bridge_token: str, api_address: str | None = None
) -> ConnectionResult:
    """Call GET {base_url}/bridge/connection with this bridge's own token.

    Nothing is enrolled: the token this installation already holds is what
    proves it is the community's bridge. It is how a bridge finds its broker
    again when the building changed how it is reached (a Turzi Stack that
    started serving over TLS, or moved). Raises EnrollmentError with a stable
    code: `token_revoked` when the API no longer knows this bridge.
    """
    try:
        async with async_request(
            hass, "GET", base_url, api_address, "/bridge/connection",
            headers={"Authorization": f"Bearer {bridge_token}"}, timeout=ENROLL_TIMEOUT,
        ) as resp:
            if resp.status == 401:
                raise EnrollmentError("token_revoked")
            if resp.status != 200:
                try:
                    code = (await resp.json()).get("error")
                except Exception:  # noqa: BLE001 — an empty or non-JSON body
                    code = None
                _LOGGER.error("Asking for the connection failed with HTTP %s (server code: %s)", resp.status, code or "none")
                raise EnrollmentError(code if isinstance(code, str) else "cannot_connect")
            body = await resp.json()
    except EnrollmentError:
        raise
    except (aiohttp.ClientError, TimeoutError) as err:
        _LOGGER.error("Asking for the connection failed: %s", err)
        raise EnrollmentError("cannot_connect") from err

    try:
        mqtt = body["mqtt"]
        api = body.get("api") or {}
        return ConnectionResult(
            mqtt_host=mqtt["host"],
            mqtt_port=int(mqtt.get("port", 1883)),
            mqtt_tls=bool(mqtt.get("tls", False)),
            mqtt_username=mqtt["username"],
            mqtt_password=mqtt["password"],
            mqtt_tls_server_name=str(mqtt["tls_server_name"]) if mqtt.get("tls_server_name") else None,
            api_base_url=str(api["base_url"]) if api.get("base_url") else None,
            api_address=str(api["address"]) if api.get("address") else None,
            title=entry_title(body.get("names")),
        )
    except (KeyError, TypeError, ValueError) as err:
        _LOGGER.error("Malformed connection answer: %s", err)
        raise EnrollmentError("cannot_connect") from err


def connection_data(found: ConnectionResult, base_url: str, address: str | None) -> dict:
    """The entry's fields for a connection the API gave: the Refresh step's and a refused login's."""
    return {
        CONF_BROKER: found.mqtt_host,
        CONF_PORT: found.mqtt_port,
        CONF_USERNAME: found.mqtt_username,
        CONF_PASSWORD: found.mqtt_password,
        CONF_USE_TLS: found.mqtt_tls,
        CONF_TLS_SERVER_NAME: found.mqtt_tls_server_name,
        CONF_API_BASE_URL: found.api_base_url or base_url,
        CONF_API_ADDRESS: found.api_address or address,
    }
