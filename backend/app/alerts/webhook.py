"""Sends an alert to a user's webhook URL, signed with HMAC-SHA256."""

import asyncio
import hashlib
import hmac
import json
import time
from collections.abc import Awaitable, Callable

import httpx

from app.alerts.message import AlertMessage, AlertSendError
from app.services.checker import USER_AGENT, PinnedTransport
from app.services.ssrf import UrlNotAllowed, ValidatedTarget, validate_url

TIMEOUT_SECONDS = 10
SIGNATURE_HEADER = "X-UptimeGlass-Signature"
TIMESTAMP_HEADER = "X-UptimeGlass-Timestamp"

Validator = Callable[[str], Awaitable[ValidatedTarget]]


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """The receiver recomputes this from the shared secret to check who sent the request."""
    message = timestamp.encode() + b"." + body
    return "sha256=" + hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


async def send_webhook(
    config: dict, message: AlertMessage, validator: Validator | None = None
) -> None:
    validate = validator or validate_url
    url = config["url"]
    try:
        # Checked again now, because DNS may have changed since the channel was created.
        target = await validate(url)
    except UrlNotAllowed as error:
        raise AlertSendError(str(error)) from None

    body = json.dumps(message.to_payload(), separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        TIMESTAMP_HEADER: timestamp,
        SIGNATURE_HEADER: sign(config["secret"], timestamp, body),
    }

    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            for ip in target.ips:
                try:
                    async with httpx.AsyncClient(
                        transport=PinnedTransport(ip),  # connect to the validated address
                        follow_redirects=False,
                        trust_env=False,
                        timeout=TIMEOUT_SECONDS,
                    ) as client:
                        # stream(): we only need the status, so the body is never downloaded.
                        async with client.stream("POST", url, content=body, headers=headers) as r:
                            status = r.status_code
                except httpx.ConnectError:
                    continue  # try the next address
                if not 200 <= status < 300:
                    raise AlertSendError(f"The webhook answered with status {status}.")
                return
    except TimeoutError:
        raise AlertSendError("The webhook did not answer in time.") from None
    except httpx.HTTPError as error:
        raise AlertSendError(f"The webhook request failed ({type(error).__name__}).") from None
    raise AlertSendError("Could not connect to the webhook.")
