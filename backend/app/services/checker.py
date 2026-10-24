"""Runs ONE check against a URL. Network code only: no database access.

SSRF rules (see ssrf.py): every request, including each redirect, is validated again, and we
connect to the validated IP address instead of letting the HTTP client look the name up.
"""

import asyncio
import ssl
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin

import certifi
import httpcore
import httpx

from app.services.ssrf import HostNotResolved, UrlNotAllowed, ValidatedTarget, validate_url

MAX_REDIRECTS = 5
MAX_BODY_BYTES = 1_000_000  # we never read more than this, even for keyword checks
MAX_DETAIL_LENGTH = 500
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
USER_AGENT = "UptimeGlass/1.0 (+https://github.com/anvesha-garg/uptimeglass)"

# Loading the certificate bundle is slow (it reads a file), so it is done ONCE and shared.
# The default context verifies certificates and host names.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

# Takes a URL and returns the validated target. Tests pass a fake one.
Validator = Callable[[str], Awaitable[ValidatedTarget]]


@dataclass(frozen=True)
class CheckOutcome:
    success: bool
    status_code: int | None = None
    latency_ms: int | None = None
    error_type: str | None = None  # timeout|dns|connection|ssl|status_code|keyword|blocked
    error_detail: str | None = None
    ssl_expires_at: datetime | None = None


@dataclass(frozen=True)
class _Response:
    status_code: int
    location: str | None
    body: str
    ssl_expires_at: datetime | None


class _Failure(Exception):
    """Internal: stops the check with a known error type."""

    def __init__(self, error_type: str, detail: str) -> None:
        super().__init__(detail)
        self.error_type = error_type
        self.detail = detail


class PinnedBackend(httpcore.AnyIOBackend):
    """Opens every TCP connection to one fixed IP, whatever host name was asked for."""

    def __init__(self, ip: str) -> None:
        self._ip = ip

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        # "host" is ignored on purpose. TLS still verifies the certificate against the
        # original host name, because httpcore passes that to start_tls separately.
        return await super().connect_tcp(
            self._ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class PinnedTransport(httpx.AsyncHTTPTransport):
    def __init__(self, ip: str) -> None:
        # Passing the shared context stops httpx from building (and loading) its own.
        super().__init__(verify=_SSL_CONTEXT)
        # Replace the connection pool httpx built with one that uses our pinned backend.
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=_SSL_CONTEXT,
            max_connections=1,
            network_backend=PinnedBackend(ip),
        )


def certificate_expiry(ssl_object) -> datetime | None:
    """Expiry date of the server certificate, or None if there is no (readable) certificate."""
    if ssl_object is None:
        return None
    try:
        not_after = ssl_object.getpeercert()["notAfter"]
        return datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), UTC)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def is_ssl_error(error: BaseException) -> bool:
    """True if an SSL error is anywhere in the exception chain (httpx wraps the real cause)."""
    current: BaseException | None = error
    for _ in range(10):  # the limit protects against a looping chain
        if current is None:
            return False
        if isinstance(current, ssl.SSLError):
            return True
        current = current.__cause__ or current.__context__
    return False


def _describe(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"[:MAX_DETAIL_LENGTH]


async def _read_capped(response: httpx.Response) -> str:
    chunks: list[bytes] = []
    size = 0
    # aiter_bytes yields decoded data, so a compressed "zip bomb" is capped too.
    async for chunk in response.aiter_bytes():
        chunks.append(chunk)
        size += len(chunk)
        if size >= MAX_BODY_BYTES:
            break
    return b"".join(chunks)[:MAX_BODY_BYTES].decode("utf-8", errors="replace")


async def _fetch(url: str, method: str, ip: str, timeout_seconds: int, read_body: bool):
    async with httpx.AsyncClient(
        transport=PinnedTransport(ip),
        follow_redirects=False,  # we follow redirects ourselves, to validate each hop
        trust_env=False,  # ignore HTTP_PROXY and similar variables
        timeout=timeout_seconds,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        async with client.stream(method, url) as response:
            stream = response.extensions.get("network_stream")
            ssl_expires_at = None
            if stream is not None:
                ssl_expires_at = certificate_expiry(stream.get_extra_info("ssl_object"))
            body = ""
            if read_body and response.status_code not in REDIRECT_STATUSES:
                body = await _read_capped(response)
            return _Response(
                status_code=response.status_code,
                location=response.headers.get("location"),
                body=body,
                ssl_expires_at=ssl_expires_at,
            )


async def _validate(validate: Validator, url: str) -> ValidatedTarget:
    try:
        return await validate(url)
    except HostNotResolved as error:  # must come before UrlNotAllowed (its parent)
        raise _Failure("dns", str(error)) from None
    except UrlNotAllowed as error:
        raise _Failure("blocked", str(error)) from None


async def _fetch_from_any_ip(url, method, target, timeout_seconds, read_body) -> _Response:
    last_error: Exception | None = None
    for ip in target.ips:
        try:
            return await _fetch(url, method, ip, timeout_seconds, read_body)
        except httpx.ConnectError as error:
            if is_ssl_error(error):
                # A bad certificate is a real answer, not a reason to try another address.
                raise _Failure("ssl", _describe(error)) from None
            last_error = error  # could not connect: try the next address
    raise _Failure("connection", _describe(last_error) if last_error else "Could not connect.")


async def _follow_redirects(url, method, timeout_seconds, expected_status, read_body, validate):
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        target = await _validate(validate, current)
        response = await _fetch_from_any_ip(current, method, target, timeout_seconds, read_body)
        follows = (
            response.status_code in REDIRECT_STATUSES
            and response.location
            and response.status_code != expected_status  # the monitor may expect the redirect
        )
        if not follows:
            return response
        current = urljoin(current, response.location)
    raise _Failure("connection", f"More than {MAX_REDIRECTS} redirects.")


def _failed(error_type, detail, started, status_code=None, ssl_expires_at=None) -> CheckOutcome:
    return CheckOutcome(
        success=False,
        status_code=status_code,
        latency_ms=int((time.perf_counter() - started) * 1000),
        error_type=error_type,
        error_detail=detail[:MAX_DETAIL_LENGTH],
        ssl_expires_at=ssl_expires_at,
    )


async def run_check(
    url: str,
    *,
    method: str = "GET",
    timeout_seconds: int = 10,
    expected_status: int = 200,
    keyword: str | None = None,
    validator: Validator | None = None,
) -> CheckOutcome:
    validate = validator or validate_url
    started = time.perf_counter()
    try:
        # One overall limit for the whole check, including every redirect.
        async with asyncio.timeout(timeout_seconds):
            final = await _follow_redirects(
                url, method, timeout_seconds, expected_status, keyword is not None, validate
            )
    except (TimeoutError, httpx.TimeoutException):
        return _failed("timeout", f"No answer within {timeout_seconds} seconds.", started)
    except _Failure as failure:
        return _failed(failure.error_type, failure.detail, started)
    except httpx.TransportError as error:
        return _failed("connection", _describe(error), started)

    if final.status_code != expected_status:
        detail = f"Expected status {expected_status}, got {final.status_code}."
        return _failed("status_code", detail, started, final.status_code, final.ssl_expires_at)
    if keyword is not None and keyword.lower() not in final.body.lower():
        detail = "The keyword was not found in the response."
        return _failed("keyword", detail, started, final.status_code, final.ssl_expires_at)

    return CheckOutcome(
        success=True,
        status_code=final.status_code,
        latency_ms=int((time.perf_counter() - started) * 1000),
        ssl_expires_at=final.ssl_expires_at,
    )
