import asyncio
import socket
import ssl
from datetime import UTC, datetime
from functools import partial
from urllib.parse import urlsplit

import httpx
import pytest

from app.services.checker import MAX_BODY_BYTES, certificate_expiry, is_ssl_error, run_check
from app.services.ssrf import ValidatedTarget, parse_url, validate_url

# This name does not exist in DNS. Our fake validator "resolves" it to 127.0.0.1, so the
# tests prove the checker connects to the validated IP while sending the original Host header.
TEST_HOST = "test.example"
BIG_TOTAL = 2_000_006  # 2,000,000 letters "a" followed by "needle"


async def validator(url: str) -> ValidatedTarget:
    if urlsplit(url).hostname == TEST_HOST:
        scheme, host, port = parse_url(url)
        return ValidatedTarget(url=url, scheme=scheme, host=host, port=port, ips=("127.0.0.1",))
    return await validate_url(url)  # everything else goes through the real guard


async def send(writer, status, body=b"", headers=None, head_only=False, length=None):
    reason = {200: "OK", 302: "Found", 404: "Not Found", 500: "Internal Server Error"}
    lines = [
        f"HTTP/1.1 {status} {reason.get(status, 'Status')}",
        f"Content-Length: {len(body) if length is None else length}",
        "Connection: close",
    ]
    lines += [f"{name}: {value}" for name, value in (headers or {}).items()]
    writer.write(("\r\n".join(lines) + "\r\n\r\n").encode())
    if not head_only:
        writer.write(body)
    await writer.drain()


async def handle(reader, writer):
    try:
        head = await reader.readuntil(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        method, path, _ = lines[0].split(" ", 2)
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                name, value = line.split(":", 1)
                headers[name.lower()] = value.strip()
        head_only = method == "HEAD"

        if path == "/ok":
            await send(writer, 200, b"hello world", head_only=head_only)
        elif path == "/host":
            await send(writer, 200, headers["host"].encode())
        elif path.startswith("/status/"):
            await send(writer, int(path.rsplit("/", 1)[1]), b"status")
        elif path == "/redirect":
            await send(writer, 302, headers={"Location": "/ok"})
        elif path == "/redirect-loop":
            await send(writer, 302, headers={"Location": "/redirect-loop"})
        elif path == "/redirect-private":
            await send(writer, 302, headers={"Location": "http://169.254.169.254/latest/"})
        elif path == "/slow":
            # Never answers. Ends when the client gives up and closes the connection.
            await asyncio.wait_for(reader.read(1), timeout=10)
        elif path == "/big":
            await send(writer, 200, length=BIG_TOTAL)
            for _ in range(20):
                writer.write(b"a" * 100_000)
                await writer.drain()
            writer.write(b"needle")
            await writer.drain()
        else:
            await send(writer, 404, b"not found")
    except (OSError, asyncio.IncompleteReadError, TimeoutError):
        pass  # the client hung up, which is expected in some tests
    finally:
        writer.close()


@pytest.fixture
async def port():
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    yield server.sockets[0].getsockname()[1]
    server.close()


async def check(port, path, **options):
    settings = {"timeout_seconds": 5, "validator": validator}
    settings.update(options)
    return await run_check(f"http://{TEST_HOST}:{port}{path}", **settings)


# ---------- helpers ----------


def test_ssl_error_is_found_in_the_cause_chain():
    outer = httpx.ConnectError("connect failed")
    outer.__cause__ = ssl.SSLCertVerificationError("certificate has expired")
    assert is_ssl_error(outer) is True


def test_plain_connect_error_is_not_an_ssl_error():
    assert is_ssl_error(httpx.ConnectError("connection refused")) is False


class FakeSslObject:
    def __init__(self, cert=None, error=None):
        self.cert = cert
        self.error = error

    def getpeercert(self):
        if self.error:
            raise self.error
        return self.cert


def test_certificate_expiry_is_parsed():
    fake = FakeSslObject({"notAfter": "Jun  1 12:00:00 2030 GMT"})
    assert certificate_expiry(fake) == datetime(2030, 6, 1, 12, 0, tzinfo=UTC)


def test_certificate_expiry_without_tls_is_none():
    assert certificate_expiry(None) is None


def test_certificate_expiry_with_missing_field_is_none():
    assert certificate_expiry(FakeSslObject({})) is None


def test_certificate_expiry_with_unreadable_certificate_is_none():
    assert certificate_expiry(FakeSslObject(error=ValueError("no certificate"))) is None


# ---------- successful checks ----------


async def test_successful_check(port):
    outcome = await check(port, "/ok")
    assert outcome.success is True
    assert outcome.status_code == 200
    assert outcome.latency_ms is not None and outcome.latency_ms >= 0
    assert outcome.error_type is None
    assert outcome.ssl_expires_at is None  # plain http has no certificate


async def test_connects_to_the_validated_ip_but_sends_the_original_host(port):
    outcome = await check(port, "/host", keyword=f"{TEST_HOST}:{port}")
    assert outcome.success is True


async def test_head_method_works(port):
    outcome = await check(port, "/ok", method="HEAD")
    assert outcome.success is True
    assert outcome.status_code == 200


# ---------- status codes and redirects ----------


async def test_unexpected_status_is_a_status_code_failure(port):
    outcome = await check(port, "/status/500")
    assert outcome.success is False
    assert outcome.status_code == 500
    assert outcome.error_type == "status_code"
    assert "500" in outcome.error_detail


async def test_redirects_are_followed(port):
    outcome = await check(port, "/redirect")
    assert outcome.success is True
    assert outcome.status_code == 200


async def test_redirect_is_not_followed_when_the_monitor_expects_it(port):
    outcome = await check(port, "/redirect", expected_status=302)
    assert outcome.success is True
    assert outcome.status_code == 302


async def test_redirect_loop_stops_after_five_redirects(port):
    # A generous timeout: six requests must finish before the redirect limit can trigger.
    outcome = await check(port, "/redirect-loop", timeout_seconds=30)
    assert outcome.success is False
    assert outcome.error_type == "connection"
    assert "redirects" in outcome.error_detail


# ---------- SSRF guard inside the checker ----------


async def test_redirect_to_a_private_address_is_blocked(port):
    outcome = await check(port, "/redirect-private")
    assert outcome.success is False
    assert outcome.error_type == "blocked"


async def test_private_address_is_blocked_by_the_real_guard(port):
    outcome = await run_check(f"http://127.0.0.1:{port}/ok")
    assert outcome.success is False
    assert outcome.error_type == "blocked"


# ---------- network failures ----------


async def test_unresolvable_host_is_a_dns_failure():
    async def no_answer(host, port):
        raise socket.gaierror("name not found")

    outcome = await run_check(
        "http://nope.example", validator=partial(validate_url, resolver=no_answer)
    )
    assert outcome.success is False
    assert outcome.error_type == "dns"


async def test_refused_connection_is_a_connection_failure():
    # Port 1 has no server on it.
    outcome = await run_check(f"http://{TEST_HOST}:1/", timeout_seconds=5, validator=validator)
    assert outcome.success is False
    assert outcome.error_type == "connection"


async def test_slow_server_is_a_timeout(port):
    outcome = await check(port, "/slow", timeout_seconds=1)
    assert outcome.success is False
    assert outcome.error_type == "timeout"


# ---------- keyword and body size ----------


async def test_keyword_is_found_ignoring_case(port):
    outcome = await check(port, "/ok", keyword="HELLO")
    assert outcome.success is True


async def test_missing_keyword_is_a_keyword_failure(port):
    outcome = await check(port, "/ok", keyword="goodbye")
    assert outcome.success is False
    assert outcome.status_code == 200
    assert outcome.error_type == "keyword"


async def test_keyword_beyond_the_size_cap_is_not_found(port):
    assert MAX_BODY_BYTES < BIG_TOTAL
    outcome = await check(port, "/big", keyword="needle")
    assert outcome.success is False
    assert outcome.error_type == "keyword"


async def test_big_response_without_keyword_is_fine(port):
    outcome = await check(port, "/big")
    assert outcome.success is True
