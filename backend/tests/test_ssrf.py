import asyncio
import socket

import pytest

from app.services import ssrf
from app.services.ssrf import UrlNotAllowed, is_blocked_ip, parse_url, validate_url

BLOCKED_IPS = [
    "127.0.0.1",  # loopback
    "127.1.2.3",
    "10.0.0.1",  # private (RFC1918)
    "172.16.0.1",
    "172.31.255.255",
    "192.168.1.1",
    "169.254.169.254",  # cloud metadata (link-local)
    "100.64.0.1",  # CGNAT
    "100.127.255.255",
    "0.0.0.0",  # unspecified
    "224.0.0.1",  # multicast
    "239.255.255.255",
    "255.255.255.255",  # broadcast
    "240.0.0.1",  # reserved
    "198.18.0.1",  # benchmarking
    "::1",  # IPv6 loopback
    "::",  # IPv6 unspecified
    "fe80::1",  # IPv6 link-local
    "fc00::1",  # IPv6 private
    "fd12:3456::1",
    "ff02::1",  # IPv6 multicast
    "::ffff:127.0.0.1",  # IPv4 hidden inside IPv6
    "::ffff:10.0.0.1",
    "::ffff:169.254.169.254",
    "64:ff9b::7f00:1",  # NAT64 wrapping 127.0.0.1
    "2002:7f00:1::1",  # 6to4 wrapping 127.0.0.1
    "::7f00:1",  # old IPv4-compatible form
    "fe80::1%eth0",  # with a zone id
    "not-an-ip",  # unreadable means blocked
    "",
]

ALLOWED_IPS = [
    "8.8.8.8",
    "1.1.1.1",
    "93.184.216.34",
    "2606:4700:4700::1111",
    "2001:4860:4860::8888",
    "::ffff:8.8.8.8",  # a public IPv4 inside IPv6 is fine
]

BAD_URLS = [
    "",
    "example.com",  # no scheme
    "//example.com",
    "ftp://example.com",
    "file:///etc/passwd",
    "gopher://example.com",
    "javascript:alert(1)",
    "http://",
    "http:///path",
    "http://user:pass@example.com",
    "http://user@example.com",
    "http://example.com\\@127.0.0.1",  # backslash trick
    "http://exa mple.com",
    "http://example.com:99999",
    "http://example.com:abc",
    "http://example.com:0",
    "http://[::1",
    "http://example.com/\n",
    "http://example.com/" + "a" * 2100,
]

GOOD_URLS = [
    ("http://example.com", ("http", "example.com", 80)),
    ("HTTPS://Example.COM/path?x=1", ("https", "example.com", 443)),
    ("http://example.com:8080/a", ("http", "example.com", 8080)),
    ("http://[2606:4700:4700::1111]/", ("http", "2606:4700:4700::1111", 80)),
]

# Disguised "this machine" addresses. They need no internet, so tests stay offline.
TRICK_URLS = [
    "http://127.0.0.1/",
    "http://127.0.0.1:8000/health",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/",
    "http://2130706433/",  # 127.0.0.1 written as one number
    "http://0x7f.1/",  # 127.0.0.1 written in hex
    "http://localhost:8000/",
    "http://0.0.0.0/",
]


def fake_resolver(answers: dict[str, list[str]]):
    """A resolver that never touches the network."""

    async def resolve(host: str, port: int) -> list[str]:
        if host not in answers:
            raise socket.gaierror("name not found")
        return answers[host]

    return resolve


# ---------- is_blocked_ip ----------


@pytest.mark.parametrize("ip", BLOCKED_IPS)
def test_blocked_addresses(ip):
    assert is_blocked_ip(ip) is True


@pytest.mark.parametrize("ip", ALLOWED_IPS)
def test_public_addresses_are_allowed(ip):
    assert is_blocked_ip(ip) is False


# ---------- parse_url ----------


@pytest.mark.parametrize("url", BAD_URLS)
def test_bad_urls_are_rejected(url):
    with pytest.raises(UrlNotAllowed):
        parse_url(url)


@pytest.mark.parametrize(("url", "expected"), GOOD_URLS)
def test_good_urls_are_parsed(url, expected):
    assert parse_url(url) == expected


# ---------- validate_url ----------


async def test_public_host_is_accepted():
    resolver = fake_resolver({"example.com": ["93.184.216.34"]})
    target = await validate_url("https://example.com/status", resolver=resolver)
    assert target.url == "https://example.com/status"
    assert (target.scheme, target.host, target.port) == ("https", "example.com", 443)
    assert target.ips == ("93.184.216.34",)


async def test_host_name_that_resolves_to_a_private_ip_is_rejected():
    resolver = fake_resolver({"intranet.example.com": ["10.0.0.5"]})
    with pytest.raises(UrlNotAllowed):
        await validate_url("http://intranet.example.com", resolver=resolver)


async def test_one_bad_answer_rejects_the_whole_host():
    resolver = fake_resolver({"mixed.example.com": ["8.8.8.8", "169.254.169.254"]})
    with pytest.raises(UrlNotAllowed):
        await validate_url("http://mixed.example.com", resolver=resolver)


async def test_unresolvable_host_is_rejected():
    with pytest.raises(UrlNotAllowed):
        await validate_url("http://nope.example.com", resolver=fake_resolver({}))


async def test_empty_dns_answer_is_rejected():
    resolver = fake_resolver({"empty.example.com": []})
    with pytest.raises(UrlNotAllowed):
        await validate_url("http://empty.example.com", resolver=resolver)


async def test_slow_dns_is_rejected(monkeypatch):
    async def slow_resolver(host: str, port: int) -> list[str]:
        await asyncio.sleep(1)
        return ["8.8.8.8"]

    monkeypatch.setattr(ssrf, "DNS_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(UrlNotAllowed):
        await validate_url("http://slow.example.com", resolver=slow_resolver)


@pytest.mark.parametrize("url", TRICK_URLS)
async def test_disguised_local_addresses_are_rejected_by_the_real_resolver(url):
    # Depending on the operating system, a trick address is either resolved to a blocked IP
    # or not resolved at all. Both end in the same rejection.
    with pytest.raises(UrlNotAllowed):
        await validate_url(url)
