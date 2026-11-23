"""Reaching a Turzi Stack inside its building: by its address, verified for its name.

A Stack has a certificate for a public name that points at its address in the
building (turzi-apps BUILDING_TLS.md §4.1). Asking DNS for that name fails
with the internet down, and on networks whose DNS refuses names that point
inside. So the bridge dials the address it was given and requires a
certificate that is valid for the name. The name through DNS is the second
try, and is how a Stack whose address changed is found again.
"""

from __future__ import annotations

import asyncio
import logging
import re
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from ipaddress import ip_address
from typing import Any

import aiohttp
import certifi
from yarl import URL

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# A Turzi Stack's name: one label of its own under an environment's Stack zone.
# Production's is `<id>.stack.turzi.cloud`; since 23/11 dev's and staging's are
# `<id>.stack-dev.turzi.cloud` and `<id>.stack-staging.turzi.cloud` (turzi-apps
# A10b, #2096), and before that `<id>.<env>.stack.turzi.cloud`, still accepted
# so a bridge can verify the name it holds until it learns the new one. Only the
# platform can have a public certificate issued for such a name: the zones are ours.
_STACK_NAME = re.compile(r"^[a-z0-9]+(\.[a-z0-9-]+\.stack|\.stack-[a-z0-9]+|\.stack)\.turzi\.cloud$")
_DISCOVER_TIMEOUT = 10


class _NamedContext(ssl.SSLContext):
    """Verifies the certificate for one given name, whatever host is dialled.

    Only the name it is asked to check is ours to give: the chain, the dates
    and the match itself are Python's own verification, unchanged.
    """

    verify_as: str = ""

    def wrap_socket(self, sock, *args, server_hostname=None, **kwargs):  # noqa: ANN001, ARG002
        return super().wrap_socket(sock, *args, server_hostname=self.verify_as, **kwargs)

    def wrap_bio(self, incoming, outgoing, *args, server_hostname=None, **kwargs):  # noqa: ANN001, ARG002
        return super().wrap_bio(incoming, outgoing, *args, server_hostname=self.verify_as, **kwargs)


def _authorities() -> str:
    """The certificate authorities trusted for a Stack: the ones Home Assistant itself ships."""
    return certifi.where()


def stack_context(name: str) -> ssl.SSLContext:
    """A context for one Stack's name. Reads files: build it off the event loop."""
    context = _NamedContext(ssl.PROTOCOL_TLS_CLIENT)
    context.verify_as = name
    # As strict as Python's own default context.
    context.verify_flags |= getattr(ssl, "VERIFY_X509_STRICT", 0) | getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", 0)
    context.load_verify_locations(_authorities())
    return context


async def async_stack_context(hass: HomeAssistant, name: str) -> ssl.SSLContext:
    """One context per name, built once, in the executor."""
    kept: dict[str, ssl.SSLContext] = hass.data.setdefault(f"{DOMAIN}_tls", {})
    if name not in kept:
        kept[name] = await hass.async_add_executor_job(stack_context, name)
    return kept[name]


def _is_address(host: str) -> bool:
    try:
        ip_address(host)
    except ValueError:
        return False
    return True


def ways(base_url: str, address: str | None) -> list[tuple[str, str | None]]:
    """Where to call, in order: each URL with the name to verify when it is not the URL's own host.

    By the address first, when one is known and the URL is HTTPS for a name.
    Then the URL as it is.
    """
    url = URL(base_url)
    host = url.host or ""
    if not address or url.scheme != "https" or host == address or _is_address(host):
        return [(base_url, None)]
    return [(str(url.with_host(address)), host), (base_url, None)]


@asynccontextmanager
async def async_post(
    hass: HomeAssistant, base_url: str, address: str | None, path: str, **kwargs: Any
) -> AsyncIterator[aiohttp.ClientResponse]:
    """POST to the API as this installation reaches it: through the Stack by its address, or as the URL says."""
    async with async_request(hass, "POST", base_url, address, path, **kwargs) as response:
        yield response


@asynccontextmanager
async def async_request(
    hass: HomeAssistant, method: str, base_url: str, address: str | None, path: str, **kwargs: Any
) -> AsyncIterator[aiohttp.ClientResponse]:
    """One call to the API as this installation reaches it."""
    session = async_get_clientsession(hass)
    unreachable: aiohttp.ClientConnectorError | None = None
    for url, name in ways(base_url, address):
        extra: dict[str, Any] = {}
        if name:
            extra = {"ssl": await async_stack_context(hass, name), "server_hostname": name}
        try:
            response = await session.request(method, f"{url.rstrip('/')}{path}", **extra, **kwargs)
        except aiohttp.ClientConnectorError as err:
            # Nobody at that address, or somebody who is not the Stack: the next way.
            unreachable = err
            continue
        try:
            yield response
        finally:
            response.release()
        return
    assert unreachable is not None
    raise unreachable


def is_stack_name(name: str) -> bool:
    """A name a Turzi Stack can hold, and nothing else's."""
    return bool(_STACK_NAME.match(name))


def _chain_context() -> ssl.SSLContext:
    """Verifies the chain and the dates, not a name: the name is what is being learned."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_REQUIRED
    context.verify_flags |= getattr(ssl, "VERIFY_X509_STRICT", 0) | getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", 0)
    context.load_verify_locations(_authorities())
    return context


def stack_name_in(certificate: dict[str, Any]) -> str | None:
    """The one Stack name a verified certificate is for, or None."""
    names = {value.lower() for kind, value in certificate.get("subjectAltName", ()) if kind == "DNS"}
    found = [name for name in names if is_stack_name(name)]
    return found[0] if len(found) == 1 else None


async def async_stack_name_at(hass: HomeAssistant, address: str, port: int) -> str | None:
    """The name of the Stack serving TLS at this address, read from its certificate.

    For a bridge that knew its Stack while it still served in clear: once the
    Stack has its certificate it closes every clear port (BUILDING_TLS.md D4),
    the bridge's way to ask for its connection included, and the name to
    verify is in the answer it can no longer get. The address is the one this
    installation already trusted; the certificate must chain to a public
    authority and be for a Stack's name, which only the platform can obtain.
    Calls made with the name are then verified for it as any other.
    """
    context = await hass.async_add_executor_job(_chain_context)
    writer = None
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(address, port, ssl=context),
            _DISCOVER_TIMEOUT,
        )
        certificate = writer.get_extra_info("peercert") or {}
    except (OSError, ssl.SSLError, TimeoutError) as err:
        _LOGGER.debug("No Turzi Stack with a trusted certificate at %s:%s (%s)", address, port, err)
        return None
    finally:
        if writer is not None:
            writer.close()
    name = stack_name_in(certificate)
    if name is None:
        _LOGGER.warning("The certificate at %s:%s is not a Turzi Stack's; not using it", address, port)
    return name


async def async_stack_moved_to_tls(hass: HomeAssistant, base_url: str) -> tuple[str, str] | None:
    """Where to ask now, when the Stack this bridge called in clear serves only TLS.

    Returns the API's base URL by the Stack's name and the address to dial, or
    None when the URL was not a Stack's in clear or nobody there is a Stack.
    """
    url = URL(base_url)
    if url.scheme != "http" or not url.host or not _is_address(url.host) or url.explicit_port is None:
        return None
    name = await async_stack_name_at(hass, url.host, url.explicit_port)
    if name is None:
        return None
    return str(url.with_scheme("https").with_host(name)), url.host


async def async_stack_renamed(hass: HomeAssistant, base_url: str, address: str | None) -> tuple[str, str] | None:
    """Where to ask now, when the Stack this bridge reaches by its address holds another name (#2096).

    A Stack's name can change (an environment's Stack zone moved, the Stack
    was given a new one). The bridge keeps dialling the address and verifying
    the old name, which the certificate there no longer carries, and the old
    name may not resolve any more: neither of its ways reaches the API to ask
    for the new connection. So the name is read from the certificate at the
    address this installation already trusted, under the same rule as
    async_stack_moved_to_tls: it must chain to a public authority and be a
    Stack's name, which only the platform can obtain. And it must be the SAME
    Stack: the first label, the Stack's id, unchanged, only the zone after it
    different. Any genuine Stack's certificate chains and matches the rule, so
    without that whoever held another Stack's key at this address could move
    the bridge to their Stack and be sent its token (QA Lead's read, #2096).
    The answer then comes through the Stack, as every call by its name does.

    Returns the API's base URL by the new name and the address to dial, or
    None when the URL is not a Stack's by name, no address is known, or the
    certificate there names no Stack, the same name, or another Stack.
    """
    url = URL(base_url)
    host = url.host or ""
    if url.scheme != "https" or not address or not is_stack_name(host) or url.port is None:
        return None
    name = await async_stack_name_at(hass, address, url.port)
    if name is None or name == host:
        return None
    if name.split(".", 1)[0] != host.split(".", 1)[0]:
        _LOGGER.warning("The certificate at %s is for another Turzi Stack (%s, not %s); not moving to it", address, name, host)
        return None
    return str(url.with_host(name)), address
