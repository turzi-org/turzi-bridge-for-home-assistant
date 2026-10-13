"""Reaching a Turzi Stack inside its building: by its address, verified for its name.

A Stack has a certificate for a public name that points at its address in the
building (turzi-apps BUILDING_TLS.md §4.1). Asking DNS for that name fails
with the internet down, and on networks whose DNS refuses names that point
inside. So the bridge dials the address it was given and requires a
certificate that is valid for the name. The name through DNS is the second
try, and is how a Stack whose address changed is found again.
"""

from __future__ import annotations

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
    session = async_get_clientsession(hass)
    unreachable: aiohttp.ClientConnectorError | None = None
    for url, name in ways(base_url, address):
        extra: dict[str, Any] = {}
        if name:
            extra = {"ssl": await async_stack_context(hass, name), "server_hostname": name}
        try:
            response = await session.post(f"{url.rstrip('/')}{path}", **extra, **kwargs)
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
