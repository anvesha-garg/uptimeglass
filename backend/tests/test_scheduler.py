import asyncio
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import CheckResult, Incident, Monitor, User
from app.services.checker import CheckOutcome, run_check
from app.services.ssrf import ValidatedTarget, parse_url, validate_url
from app.worker.scheduler import MonitorSnapshot, claim_due_monitors, run_cycle, run_forever

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
OK = CheckOutcome(success=True, status_code=200, latency_ms=10)
# This name is not in DNS. The validator below maps it to 127.0.0.1 for the local test server.
TEST_HOST = "test.example"


@pytest.fixture
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def make_monitor(db, **overrides) -> Monitor:
    user = User(email=f"{uuid4()}@example.com", password_hash="x")
    db.add(user)
    await db.commit()
    values = {
        "user_id": user.id,
        "name": "Site",
        "url": "https://example.com",
        "status": "UP",
        "next_check_at": NOW - timedelta(seconds=1),  # due
    }
    values.update(overrides)
    monitor = Monitor(**values)
    db.add(monitor)
    await db.commit()
    return monitor


async def count(db, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


async def ok_checker(snapshot: MonitorSnapshot) -> CheckOutcome:
    return OK


# ---------- claiming ----------


async def test_claim_returns_only_due_unpaused_monitors(db_session):
    due = await make_monitor(db_session)
    await make_monitor(db_session, next_check_at=NOW + timedelta(hours=1))  # not due yet
    await make_monitor(db_session, is_paused=True, status="PAUSED")  # due but paused

    claimed = await claim_due_monitors(db_session, NOW)
    assert [snapshot.id for snapshot in claimed] == [due.id]


async def test_claim_moves_next_check_forward_so_it_is_not_claimed_twice(db_session):
    monitor = await make_monitor(db_session, timeout_seconds=10)

    assert len(await claim_due_monitors(db_session, NOW)) == 1
    await db_session.refresh(monitor)
    assert monitor.next_check_at == NOW + timedelta(seconds=40)  # timeout 10 + 30 lease
    assert await claim_due_monitors(db_session, NOW) == []


async def test_claim_respects_the_batch_size(db_session):
    for _ in range(5):
        await make_monitor(db_session)
    assert len(await claim_due_monitors(db_session, NOW, batch_size=3)) == 3
    assert len(await claim_due_monitors(db_session, NOW, batch_size=3)) == 2


async def test_two_workers_never_claim_the_same_monitor(db_session, session_factory):
    for _ in range(6):
        await make_monitor(db_session)

    async def claim():
        async with session_factory() as db:
            return await claim_due_monitors(db, NOW, batch_size=10)

    first, second = await asyncio.gather(claim(), claim())
    ids = [snapshot.id for snapshot in first + second]
    assert len(ids) == 6  # every monitor was claimed...
    assert len(set(ids)) == 6  # ...exactly once


# ---------- running a cycle ----------


async def test_cycle_records_the_result(db_session, session_factory):
    monitor = await make_monitor(db_session, status="PENDING")

    assert await run_cycle(session_factory, ok_checker, now=NOW) == 1
    await db_session.refresh(monitor)
    assert monitor.status == "UP"
    assert monitor.last_checked_at == NOW
    assert await count(db_session, CheckResult) == 1
    # Not due again until the interval has passed.
    assert monitor.next_check_at == NOW + timedelta(seconds=monitor.interval_seconds)


async def test_cycle_limits_how_many_checks_run_at_once(db_session, session_factory):
    for _ in range(6):
        await make_monitor(db_session)
    active = 0
    peak = 0

    async def slow_checker(snapshot: MonitorSnapshot) -> CheckOutcome:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        return OK

    assert await run_cycle(session_factory, slow_checker, now=NOW, max_concurrent=2) == 6
    assert peak == 2  # concurrent, but never more than the limit
    assert await count(db_session, CheckResult) == 6


async def test_one_crashing_check_does_not_stop_the_others(db_session, session_factory):
    good = await make_monitor(db_session)
    bad = await make_monitor(db_session, url="https://crash.example.com")

    async def checker(snapshot: MonitorSnapshot) -> CheckOutcome:
        if "crash" in snapshot.url:
            raise RuntimeError("bug in the checker")
        return OK

    assert await run_cycle(session_factory, checker, now=NOW) == 2
    results = (await db_session.scalars(select(CheckResult))).all()
    assert [result.monitor_id for result in results] == [good.id]
    # The crashed monitor keeps its lease, so it is retried later instead of right away.
    await db_session.refresh(bad)
    assert bad.next_check_at > NOW


# ---------- the loop ----------


async def test_loop_checks_due_monitors_and_stops_when_asked(db_session, session_factory):
    await make_monitor(db_session, next_check_at=datetime.now(UTC) - timedelta(seconds=1))
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        run_forever(session_factory, stop_event, checker=ok_checker, poll_interval=0.05)
    )
    try:
        for _ in range(100):  # wait up to 10 seconds for the first result
            if await count(db_session, CheckResult) >= 1:
                break
            await asyncio.sleep(0.1)
    finally:
        stop_event.set()
        await asyncio.wait_for(task, timeout=10)  # a clean stop, not a cancel
    assert await count(db_session, CheckResult) == 1  # checked once, not every second


# ---------- the whole story, against a real local web server ----------


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


async def test_monitor_goes_up_down_up_with_exactly_one_incident(
    db_session, session_factory, toggle_server
):
    monitor = await make_monitor(
        db_session,
        status="PENDING",
        url=f"http://{TEST_HOST}:{toggle_server['port']}/",
        interval_seconds=60,
        timeout_seconds=10,
    )

    async def cycle(seconds: int) -> int:
        return await run_cycle(session_factory, real_checker, now=NOW + timedelta(seconds=seconds))

    async def status() -> str:
        await db_session.refresh(monitor)
        return monitor.status

    # The server is healthy: the first check makes the monitor UP.
    assert await cycle(0) == 1
    assert await status() == "UP"
    assert await cycle(30) == 0  # not due yet (next check is at 60 seconds)

    # The server breaks. One or two failures are not an outage yet.
    toggle_server["up"] = False
    assert await cycle(61) == 1
    assert await status() == "UP"
    assert await cycle(82) == 1  # re-checked after 20 seconds, not after a full interval
    assert await status() == "UP"
    assert await count(db_session, Incident) == 0

    # The third failure in a row: DOWN, and exactly one incident.
    assert await cycle(103) == 1
    assert await status() == "DOWN"
    assert await count(db_session, Incident) == 1
    assert await cycle(110) == 0  # back on the normal schedule while DOWN

    # The server recovers. One success is not enough...
    toggle_server["up"] = True
    assert await cycle(164) == 1
    assert await status() == "DOWN"
    # ...the second one is.
    assert await cycle(185) == 1
    assert await status() == "UP"

    incident = await db_session.scalar(select(Incident))
    await db_session.refresh(incident)
    assert await count(db_session, Incident) == 1
    assert incident.status == "resolved"
    assert incident.cause == "status_code"
    assert incident.started_at == NOW + timedelta(seconds=103)
    assert incident.resolved_at == NOW + timedelta(seconds=185)
    assert await count(db_session, CheckResult) == 6
