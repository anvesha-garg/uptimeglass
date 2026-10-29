import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import (
    CheckResult,
    CheckRollupHourly,
    Monitor,
    RefreshToken,
    User,
)
from app.services import retention
from app.services.retention import (
    LOCK_KEY,
    RAW_RETENTION_DAYS,
    run_retention,
    run_retention_locked,
)
from app.worker.retention_loop import run_retention_loop

NOW = datetime(2026, 6, 1, 12, 30, tzinfo=UTC)


async def make_monitor(db) -> Monitor:
    user = User(email=f"{uuid4()}@example.com", password_hash="x")
    db.add(user)
    await db.commit()
    monitor = Monitor(
        user_id=user.id, name="S", url="https://example.com", status="UP", next_check_at=NOW
    )
    db.add(monitor)
    await db.commit()
    return monitor


def result(monitor, when, success=True, latency=100):
    return CheckResult(
        monitor_id=monitor.id,
        checked_at=when,
        success=success,
        latency_ms=latency if success else None,
    )


async def count(db, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


async def test_old_results_are_rolled_up_then_pruned(db_session):
    monitor = await make_monitor(db_session)
    old = NOW - timedelta(days=RAW_RETENTION_DAYS + 5)
    db_session.add_all([result(monitor, old, latency=100), result(monitor, old, success=False)])
    db_session.add(result(monitor, NOW - timedelta(days=1)))  # recent: stays
    await db_session.commit()

    report = await run_retention(db_session, NOW)
    assert report.raw_deleted == 2
    assert await count(db_session, CheckResult) == 1

    row = await db_session.scalar(
        select(CheckRollupHourly).where(CheckRollupHourly.hour == old.replace(minute=0, second=0))
    )
    assert (row.checks, row.failures, row.avg_ms) == (2, 1, 100)  # history survives


async def test_nothing_is_deleted_when_the_rollup_fails(db_session, monkeypatch):
    monitor = await make_monitor(db_session)
    db_session.add(result(monitor, NOW - timedelta(days=RAW_RETENTION_DAYS + 5)))
    await db_session.commit()

    async def broken_rollup(*args, **kwargs):
        raise RuntimeError("rollup failed")

    monkeypatch.setattr(retention, "rollup_hours", broken_rollup)
    with pytest.raises(RuntimeError):
        await run_retention(db_session, NOW)
    assert await count(db_session, CheckResult) == 1  # raw data is untouched


async def test_cutoff_is_a_whole_hour(db_session):
    monitor = await make_monitor(db_session)
    cutoff = (NOW - timedelta(days=RAW_RETENTION_DAYS)).replace(minute=0, second=0)
    db_session.add_all(
        [
            result(monitor, cutoff - timedelta(minutes=1)),  # previous hour: deleted
            result(monitor, cutoff),  # exactly on the cutoff: kept
            result(monitor, cutoff + timedelta(minutes=10)),  # same hour: kept
        ]
    )
    await db_session.commit()

    report = await run_retention(db_session, NOW)
    assert report.raw_deleted == 1
    assert await count(db_session, CheckResult) == 2


async def test_current_hour_is_never_rolled_up(db_session):
    monitor = await make_monitor(db_session)
    db_session.add(result(monitor, NOW - timedelta(minutes=5)))  # still inside the current hour
    await db_session.commit()

    await run_retention(db_session, NOW)
    assert await count(db_session, CheckRollupHourly) == 0


async def test_running_twice_changes_nothing_more(db_session):
    monitor = await make_monitor(db_session)
    db_session.add(result(monitor, NOW - timedelta(days=2)))
    await db_session.commit()

    await run_retention(db_session, NOW)
    second = await run_retention(db_session, NOW)
    assert second.raw_deleted == 0
    assert await count(db_session, CheckRollupHourly) == 1


async def test_very_old_rollups_are_deleted(db_session):
    monitor = await make_monitor(db_session)
    db_session.add_all(
        [
            CheckRollupHourly(
                monitor_id=monitor.id, hour=NOW - timedelta(days=400), checks=1, failures=0
            ),
            CheckRollupHourly(
                monitor_id=monitor.id, hour=NOW - timedelta(days=100), checks=1, failures=0
            ),
        ]
    )
    await db_session.commit()

    report = await run_retention(db_session, NOW)
    assert report.rollups_deleted == 1
    assert await count(db_session, CheckRollupHourly) == 1


async def test_old_tokens_are_deleted_and_fresh_ones_stay(db_session):
    user = User(email="t@example.com", password_hash="x")
    db_session.add(user)
    await db_session.commit()

    def token(expires, revoked=None):
        return RefreshToken(
            user_id=user.id,
            token_hash=uuid4().hex + uuid4().hex,
            expires_at=expires,
            revoked_at=revoked,
        )

    db_session.add_all(
        [
            token(NOW - timedelta(days=3)),  # expired long ago: deleted
            token(NOW + timedelta(days=5), revoked=NOW - timedelta(days=3)),  # revoked: deleted
            token(NOW + timedelta(days=5)),  # valid: stays
            token(NOW - timedelta(hours=2)),  # just expired, inside the grace day: stays
        ]
    )
    await db_session.commit()

    report = await run_retention(db_session, NOW)
    assert report.tokens_deleted == 2
    assert await count(db_session, RefreshToken) == 2


# ---------- the lock ----------


async def test_a_second_worker_skips_while_the_lock_is_held(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as holder, factory() as other:
        await holder.scalar(text("SELECT pg_advisory_lock(:key)"), {"key": LOCK_KEY})
        assert await run_retention_locked(other, NOW) is None  # skipped, not blocked
        await holder.scalar(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})


async def test_the_lock_is_released_after_a_run(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as first:
        assert await run_retention_locked(first, NOW) is not None
    async with factory() as second:
        assert await run_retention_locked(second, NOW) is not None  # not stuck


# ---------- the loop ----------


async def test_loop_runs_and_stops_cleanly(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    stop = asyncio.Event()
    task = asyncio.create_task(run_retention_loop(factory, stop, first_delay=0.01, interval=0.05))
    await asyncio.sleep(0.3)
    stop.set()
    await asyncio.wait_for(task, timeout=5)  # exits without being cancelled


async def test_loop_survives_a_failing_run(engine, monkeypatch):
    from app.worker import retention_loop

    calls = []

    async def failing(db):
        calls.append(1)
        raise RuntimeError("boom")

    monkeypatch.setattr(retention_loop, "run_retention_locked", failing)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    stop = asyncio.Event()
    task = asyncio.create_task(run_retention_loop(factory, stop, first_delay=0.01, interval=0.05))
    await asyncio.sleep(0.4)
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    assert len(calls) >= 2  # kept trying after the first failure
