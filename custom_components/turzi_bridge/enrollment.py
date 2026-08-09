"""Turzi Bridge Cloud API client — enrollment (BRIDGE_CLOUD_API.md).

Exchanges a single-use enrollment token for everything the bridge needs:
house_id, a long-lived bridge token, and a per-home MQTT credential.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_integration

from .const import DOMAIN, PROTOCOL_VERSION

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


async def async_enroll(
    hass: HomeAssistant, base_url: str, enrollment_token: str
) -> EnrollResult:
    """Call POST {base_url}/bridge/enroll and return the provisioned config."""
    integration = await async_get_integration(hass, DOMAIN)
    payload = {
        "enrollment_token": enrollment_token.strip(),
        "bridge": {
            "type": "home-assistant",
            "bridge_version": integration.version and str(integration.version),
            "core_version": getattr(hass.config, "version", None)
            and str(hass.config.version),
            "protocol_version": PROTOCOL_VERSION,
        },
    }

    session = async_get_clientsession(hass)
    url = f"{base_url.rstrip('/')}/bridge/enroll"
    try:
        async with session.post(url, json=payload, timeout=ENROLL_TIMEOUT) as resp:
            if resp.status == 429:
                raise EnrollmentError("rate_limited")
            if resp.status in (404, 410):
                raise EnrollmentError("token_invalid")
            if resp.status == 409:
                raise EnrollmentError("home_not_ready")
            if resp.status != 200:
                _LOGGER.error("Enrollment failed with HTTP %s", resp.status)
                raise EnrollmentError("cannot_connect")
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
        )
    except (KeyError, TypeError, ValueError) as err:
        _LOGGER.error("Malformed enrollment response: %s", err)
        raise EnrollmentError("cannot_connect") from err
