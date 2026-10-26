import asyncio
import hashlib
import hmac
import json
from urllib.parse import urlsplit

import pytest

from app.alerts.message import AlertMessage, AlertSendError, make_test_message
from app.alerts.webhook import SIGNATURE_HEADER, TIMESTAMP_HEADER, send_webhook, sign
from app.services.ssrf import ValidatedTarget, parse_url, validate_url

# This name is not in DNS. The validator below maps it to 127.0.0.1 for the local test server.
TEST_HOST = "test.example"
SECRET = "s3cret"


async def validator(url: str) -> ValidatedTarget:
    if urlsplit(url).hostname == TEST_HOST:
        scheme, host, port = parse_url(url)
        return ValidatedTarget(url=url, scheme=scheme, host=host, port=port, ips=("127.0.0.1",))
    return await validate_url(url)


@pytest.fixture
async def receiver():
    """A tiny web server that records every request and answers with a chosen status."""
    state = {"status": 200, "requests": []}

    async def handle(reader, writer):
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            headers = {}
            for line in head.decode("latin-1").split("\r\n")[1:]:
                if ":" in line:
                    name, value = line.split(":", 1)
                    headers[name.lower()] = value.strip()
            body = await reader.readexactly(int(headers.get("content-length", "0")))
            state["requests"].append({"headers": headers, "body": body})
            reply = (
                f"HTTP/1.1 {state['status']} X\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            )
            writer.write(reply.encode())
            await writer.drain()
        except (OSError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    state["port"] = server.sockets[0].getsockname()[1]
    yield state
    server.close()


def config_for(port: int, host: str = TEST_HOST) -> dict:
    return {"url": f"http://{host}:{port}/hook", "secret": SECRET}


def test_sign_matches_a_hand_computed_hmac():
    body = b'{"a":1}'
    expected = hmac.new(SECRET.encode(), b"1700000000." + body, hashlib.sha256).hexdigest()
    assert sign(SECRET, "1700000000", body) == f"sha256={expected}"


async def test_webhook_is_delivered_signed(receiver):
    message = AlertMessage(
        kind="opened",
        title="Site is down",
        text="3 failed checks",
        monitor_id="m1",
        monitor_name="My site",
        url="https://example.com",
    )
    await send_webhook(config_for(receiver["port"]), message, validator=validator)

    (request,) = receiver["requests"]
    headers = request["headers"]
    timestamp = headers[TIMESTAMP_HEADER.lower()]
    # The receiver can verify the signature with the shared secret.
    assert headers[SIGNATURE_HEADER.lower()] == sign(SECRET, timestamp, request["body"])
    assert headers["content-type"] == "application/json"
    payload = json.loads(request["body"])
    assert payload["event"] == "opened"
    assert payload["monitor"] == {"id": "m1", "name": "My site", "url": "https://example.com"}


async def test_connects_to_the_validated_ip_but_sends_the_original_host(receiver):
    await send_webhook(config_for(receiver["port"]), make_test_message(), validator=validator)
    assert receiver["requests"][0]["headers"]["host"] == f"{TEST_HOST}:{receiver['port']}"


@pytest.mark.parametrize("status", [500, 404, 302])
async def test_a_non_success_status_is_an_error(receiver, status):
    receiver["status"] = status  # a redirect is not followed, so 302 counts as a failure
    with pytest.raises(AlertSendError, match=str(status)):
        await send_webhook(config_for(receiver["port"]), make_test_message(), validator=validator)


async def test_a_private_address_is_blocked_by_the_real_guard(receiver):
    config = config_for(receiver["port"], host="127.0.0.1")
    with pytest.raises(AlertSendError, match="private"):
        await send_webhook(config, make_test_message())
    assert receiver["requests"] == []  # nothing was sent


async def test_a_refused_connection_is_an_error():
    config = {"url": f"http://{TEST_HOST}:1/hook", "secret": SECRET}
    with pytest.raises(AlertSendError):
        await send_webhook(config, make_test_message(), validator=validator)
