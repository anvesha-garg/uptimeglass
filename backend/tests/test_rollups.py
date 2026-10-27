from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import CheckResult, CheckRollupHourly, Monitor, User
from app.services.analytics import (
    bucket_by_day,
    hour_floor,
    load_points,
    rollup_hours,
    summarize,
    uptime_percent,
    window_start,
)

H0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


async def make_monitor(db) -> Monitor:
    user = User(email=f"{uuid4()}@example.com", password_hash="x")
    db.add(user)
    await db.commit()
    monitor = Monitor(
        user_id=user.id, name="S", url="https://example.com", status="UP", next_check_at=H0
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
        status_code=200 if success else 500,
    )


async def rollup_rows(db) -> list[CheckRollupHourly]:
    rows = await db.scalars(
        select(CheckRollupHourly)
        .order_by(CheckRollupHourly.hour)
        .execution_options(populate_existing=True)
    )
    return list(rows)


# ---------- pure helpers ----------


@pytest.mark.parametrize(
    ("checks", "failures", "expected"),
    [(0, 0, None), (10, 0, 100.0), (10, 10, 0.0), (3, 1, 66.667), (1000, 1, 99.9)],
)
def test_uptime_percent(checks, failures, expected):
    assert uptime_percent(checks, failures) == expected


def test_hour_floor_drops_minutes():
    assert hour_floor(datetime(2026, 1, 1, 10, 42, 7, 5, tzinfo=UTC)) == H0


def test_summarize_no_points_has_no_uptime():
    s = summarize([])
    assert (s.checks, s.uptime_percent, s.avg_ms) == (0, None, None)


# ---------- rolling up ----------


async def test_rollup_computes_counts_and_percentiles(db_session):
    monitor = await make_monitor(db_session)
    for i, latency in enumerate([100, 200, 300, 400]):
        db_session.add(result(monitor, H0 + timedelta(minutes=i), latency=latency))
    db_session.add(result(monitor, H0 + timedelta(minutes=10), success=False))
    await db_session.commit()

    written = await rollup_hours(db_session, H0, H0 + timedelta(hours=1))
    assert written == 1
    (row,) = await rollup_rows(db_session)
    assert (row.checks, row.failures) == (5, 1)
    assert row.avg_ms == 250  # failures are not counted in latency
    assert row.p50_ms == 250
    assert row.p95_ms == pytest.approx(385)
    assert row.p99_ms == pytest.approx(397)


async def test_rollup_is_safe_to_run_twice(db_session):
    monitor = await make_monitor(db_session)
    db_session.add(result(monitor, H0 + timedelta(minutes=1)))
    await db_session.commit()

    await rollup_hours(db_session, H0, H0 + timedelta(hours=1))
    db_session.add(result(monitor, H0 + timedelta(minutes=2)))
    await db_session.commit()
    await rollup_hours(db_session, H0, H0 + timedelta(hours=1))

    (row,) = await rollup_rows(db_session)
    assert row.checks == 2  # refreshed, not duplicated


async def test_rollup_ignores_partial_hours_and_empty_ranges(db_session):
    monitor = await make_monitor(db_session)
    db_session.add(result(monitor, H0 + timedelta(minutes=5)))
    await db_session.commit()

    assert await rollup_hours(db_session, H0, H0) == 0  # nothing to do
    # Bounds are rounded down to whole hours, so the half hour at the end is not rolled up.
    assert await rollup_hours(db_session, H0, H0 + timedelta(minutes=30)) == 0
    assert await rollup_rows(db_session) == []


async def test_all_failed_hour_has_no_latency(db_session):
    monitor = await make_monitor(db_session)
    db_session.add(result(monitor, H0 + timedelta(minutes=1), success=False))
    await db_session.commit()

    await rollup_hours(db_session, H0, H0 + timedelta(hours=1))
    (row,) = await rollup_rows(db_session)
    assert (row.checks, row.failures) == (1, 1)
    assert row.avg_ms is None and row.p95_ms is None


async def test_each_monitor_and_hour_gets_its_own_row(db_session):
    first, second = await make_monitor(db_session), await make_monitor(db_session)
    db_session.add_all(
        [
            result(first, H0 + timedelta(minutes=1)),
            result(first, H0 + timedelta(hours=1, minutes=1)),
            result(second, H0 + timedelta(minutes=1)),
        ]
    )
    await db_session.commit()

    assert await rollup_hours(db_session, H0, H0 + timedelta(hours=2)) == 3


# ---------- reading ----------


async def test_load_points_uses_rollups_for_old_hours_and_raw_for_the_current_one(db_session):
    monitor = await make_monitor(db_session)
    now = H0 + timedelta(hours=2, minutes=30)
    db_session.add_all(
        [
            result(monitor, H0 + timedelta(minutes=1), latency=100),  # old hour, rolled up
            result(monitor, H0 + timedelta(hours=2, minutes=5), latency=300),  # current hour
        ]
    )
    await db_session.commit()
    await rollup_hours(db_session, H0, H0 + timedelta(hours=2))

    points = await load_points(db_session, monitor.id, H0, now)
    assert [(p.hour, p.checks) for p in points] == [(H0, 1), (H0 + timedelta(hours=2), 1)]


async def test_load_points_falls_back_to_raw_when_the_rollup_is_late(db_session):
    monitor = await make_monitor(db_session)
    now = H0 + timedelta(hours=3, minutes=5)
    db_session.add(result(monitor, H0 + timedelta(minutes=1)))  # never rolled up
    await db_session.commit()

    points = await load_points(db_session, monitor.id, H0, now)
    assert [(p.hour, p.checks) for p in points] == [(H0, 1)]


async def test_a_rollup_survives_after_raw_results_are_gone(db_session):
    monitor = await make_monitor(db_session)
    db_session.add(result(monitor, H0 + timedelta(minutes=1)))
    await db_session.commit()
    await rollup_hours(db_session, H0, H0 + timedelta(hours=1))

    for row in (await db_session.scalars(select(CheckResult))).all():
        await db_session.delete(row)
    await db_session.commit()

    points = await load_points(db_session, monitor.id, H0, H0 + timedelta(hours=2))
    assert summarize(points).checks == 1


async def test_summary_combines_hours_with_weighted_latency(db_session):
    monitor = await make_monitor(db_session)
    db_session.add_all(
        [result(monitor, H0 + timedelta(minutes=i), latency=100) for i in range(3)]
        + [result(monitor, H0 + timedelta(hours=1, minutes=1), latency=500)]
        + [result(monitor, H0 + timedelta(hours=1, minutes=2), success=False)]
    )
    await db_session.commit()

    points = await load_points(db_session, monitor.id, H0, H0 + timedelta(hours=3))
    s = summarize(points)
    assert (s.checks, s.failures) == (5, 1)
    assert s.uptime_percent == 80.0
    assert s.avg_ms == 200  # (3 * 100 + 1 * 500) / 4 successful checks


def test_bucket_by_day_merges_hours():
    day = datetime(2026, 1, 1, tzinfo=UTC)
    from app.services.analytics import Point

    points = [
        Point(day + timedelta(hours=1), 10, 1, 100, 100, 100, 100),
        Point(day + timedelta(hours=2), 10, 0, 200, 200, 200, 200),
        Point(day + timedelta(days=1, hours=1), 4, 4, None, None, None, None),
    ]
    first, second = bucket_by_day(points)
    assert (first.hour, first.checks, first.failures) == (day, 20, 1)
    assert (second.checks, second.failures, second.avg_ms) == (4, 4, None)


def test_window_start():
    assert window_start("24h", H0) == H0 - timedelta(hours=24)
    assert window_start("90d", H0) == H0 - timedelta(days=90)
