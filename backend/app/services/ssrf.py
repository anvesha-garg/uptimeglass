"""SSRF guard: decides whether a monitor URL is safe to request.

Rule: never trust the text of the URL. Resolve the host name to IP addresses and judge the
IPs. Phase 3 calls validate_url again before every check (and after every redirect) and
connects to one of the validated IPs, so DNS cannot change the answer in between.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

ALLOWED_SCHEMES = {"http": 80, "https": 443}  # scheme -> default port
MAX_URL_LENGTH = 2048
DNS_TIMEOUT_SECONDS = 5.0

# Ranges that Python's "is_global" does not reject, or that hide an IPv4 address inside IPv6.
EXTRA_BLOCKED_NETWORKS = [
    ipaddress.ip_network(network)
    for network in (
        "::/8",  # unspecified, loopback and the old IPv4-compatible form (::127.0.0.1)
        "64:ff9b::/96",  # NAT64: embeds an IPv4 address
        "64:ff9b:1::/48",  # local-use NAT64
        "2001::/32",  # Teredo tunnels
        "2002::/16",  # 6to4: embeds an IPv4 address
    )
]

# A resolver takes (host, port) and returns IP addresses. Tests pass a fake one.
Resolver = Callable[[str, int], Awaitable[list[str]]]


class UrlNotAllowed(Exception):
    """The URL is malformed, or it points somewhere we must never connect to."""


@dataclass(frozen=True)
class ValidatedTarget:
    url: str
    scheme: str
    host: str
    port: int
    ips: tuple[str, ...]  # every address is public; the checker connects to one of these


def is_blocked_ip(value: str) -> bool:
    """True if we must not connect to this address."""
    try:
        # Drop an IPv6 zone such as "fe80::1%eth0" before parsing.
        ip = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return True  # cannot read it, so do not trust it
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped  # ::ffff:127.0.0.1 is really 127.0.0.1
    # Multicast counts as "global" in Python, so it needs its own check.
    if ip.is_multicast or not ip.is_global:
        return True
    return any(ip in network for network in EXTRA_BLOCKED_NETWORKS)


def parse_url(url: str) -> tuple[str, str, int]:
    """Check the shape of the URL (no DNS). Returns (scheme, host, port)."""
    if len(url) > MAX_URL_LENGTH:
        raise UrlNotAllowed("The URL is too long.")
    # Backslashes, spaces and control characters are read differently by different libraries.
    # That difference is a classic way to smuggle a second host past a check.
    if "\\" in url or any(ord(char) <= 32 or ord(char) == 127 for char in url):
        raise UrlNotAllowed("The URL contains characters that are not allowed.")
    try:
        parts = urlsplit(url)
        port = parts.port  # raises ValueError for a bad port
    except ValueError:
        raise UrlNotAllowed("The URL is not valid.") from None

    if parts.scheme not in ALLOWED_SCHEMES:
        raise UrlNotAllowed("Only http and https URLs are allowed.")
    if parts.username is not None or parts.password is not None:
        raise UrlNotAllowed("URLs with a user name or password are not allowed.")
    if not parts.hostname:
        raise UrlNotAllowed("The URL has no host name.")
    if port == 0:
        raise UrlNotAllowed("The port is not valid.")
    return parts.scheme, parts.hostname, port if port is not None else ALLOWED_SCHEMES[parts.scheme]


async def system_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    # info[4][0] is the IP address. dict.fromkeys removes duplicates and keeps the order.
    return list(dict.fromkeys(info[4][0] for info in infos))


async def validate_url(url: str, resolver: Resolver | None = None) -> ValidatedTarget:
    """Return the validated target, or raise UrlNotAllowed."""
    scheme, host, port = parse_url(url)
    resolve = resolver or system_resolver
    try:
        ips = await asyncio.wait_for(resolve(host, port), timeout=DNS_TIMEOUT_SECONDS)
    except (OSError, TimeoutError, UnicodeError):
        # OSError covers "name not found". UnicodeError covers broken international names.
        raise UrlNotAllowed("The host name could not be resolved.") from None
    if not ips:
        raise UrlNotAllowed("The host name could not be resolved.")
    # Every address must be public. One private answer rejects the whole host.
    if any(is_blocked_ip(ip) for ip in ips):
        raise UrlNotAllowed("The URL points to a private or internal address.")
    return ValidatedTarget(url=url, scheme=scheme, host=host, port=port, ips=tuple(ips))
