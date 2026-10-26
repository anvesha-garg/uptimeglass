"""Phase 4 "Done when": an outage sends one opened and one resolved alert per channel."""

import asyncio
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.alerts import dispatcher
from app.models import AlertChannel, AlertEvent, Monitor, MonitorAlertChannel, User
from app.services.checker import CheckOutcome, run_check
from app.services.ssrf import ValidatedTarget, parse_url, validate_url
from app.worker.scheduler import MonitorSnapshot, run_cycle

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
# This name is not in DNS. The validator below maps it to 127.0.0.1 for the local test server.
TEST_HOST = "test.example"


@pytest.fixture
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def validator(url: str) -> ValidatedTarget:
    if urlsplit(url).hostname == TEST_HOST:
        scheme, host, port = parse_url(url)
        return ValidatedTarget(url=url, scheme=scheme, host=host, port=port, ips=("127.0.0.1",))
    return await validate_url(url)


async def real_checker(snapshot: MonitorSnapshot) -> CheckOutcome:
    return await run_check(
        snapshot.url,
        method=snapshot.method,
        timeout_seconds=snapshot.timeout_seconds,
        expected_status=snapshot.expected_status,
        keyword=snapshot.keyword,
        validator=validator,
    )


@pytest.fixture
async def toggle_server():
    """A tiny web server whose answer the test can switch between 200 and 500."""
    state = {"up": True}

    async def handle(reader, writer):
        try:
            await reader.readuntil(b"\r\n\r\n")
            status = 200 if state["up"] else 500
            body = b"ok"
            head = (
                f"HTTP/1.1 {status} X\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n"
            )
            writer.write(head.encode() + body)
            await writer.drain()
        except (OSError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    state["port"] = server.sockets[0].getsockname()[1]
    yield state
    server.close()


async def test_outage_sends_exactly_one_opened_and_one_resolved_alert_per_channel(
    db_session, session_factory, toggle_server, monkeypatch
):
    sent: list[tuple] = []

    async def fake_send(channel, message):
        sent.append((channel.id, message.kind))

    monkeypatch.setattr(dispatcher, "send_to_channel", fake_send)

    user = User(email=f"{uuid4()}@example.com", password_hash="x")
    db_session.add(user)
    await db_session.commit()
    monitor = Monitor(
        user_id=user.id,
        name="Site",
        url=f"http://{TEST_HOST}:{toggle_server['port']}/",
        status="PENDING",
        interval_seconds=60,
        timeout_seconds=10,
        next_check_at=NOW - timedelta(seconds=1),
    )
    channels = [
        AlertChannel(user_id=user.id, type="webhook", is_verified=True, config={"url": "x"})
        for _ in range(2)
    ]
    db_session.add_all([monitor, *channels])
    await db_session.commit()
    db_session.add_all(
        MonitorAlertChannel(monitor_id=monitor.id, channel_id=c.id) for c in channels
    )
    await db_session.commit()

    async def cycle(seconds: int) -> int:
        return await run_cycle(session_factory, real_checker, now=NOW + timedelta(seconds=seconds))

    # A healthy start sends nothing.
    assert await cycle(0) == 1
    assert sent == []

    # The server breaks. Alerts only start once the third failure makes the monitor DOWN.
    toggle_server["up"] = False
    await cycle(61)
    await cycle(82)
    assert sent == []
    await cycle(103)
    assert sorted(sent) == sorted((c.id, "opened") for c in channels)  # one per channel
    await cycle(110)  # not due, nothing happens

    # The server recovers: still silent after one success, then one "resolved" per channel.
    toggle_server["up"] = True
    await cycle(164)
    assert len(sent) == 2
    await cycle(185)
    assert len(sent) == 4
    assert sorted(kind for _, kind in sent) == ["opened", "opened", "resolved", "resolved"]

    events = await db_session.scalars(select(AlertEvent).execution_options(populate_existing=True))
    events = list(events)
    assert len(events) == 4
    assert all(event.success for event in events)
    total = await db_session.scalar(select(func.count()).select_from(AlertEvent))
    assert total == 4
