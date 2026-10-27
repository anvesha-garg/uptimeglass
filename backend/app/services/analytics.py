"""Hourly rollups, uptime percentages and chart data."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

WINDOWS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}


def hour_floor(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def uptime_percent(checks: int, failures: int) -> float | None:
    """None when there is no data. "No data" is not the same as "100% up"."""
    if checks <= 0:
        return None
    return round((checks - failures) / checks * 100, 3)


async def rollup_hours(db: AsyncSession, since: datetime, until: datetime) -> int:
    """Roll raw results in [since, until) into hourly rows. Safe to run again (upsert).

    Both bounds are rounded to whole hours, so a partial hour is never stored.
    Returns the number of rollup rows written.
    """
    start, end = hour_floor(since), hour_floor(until)
    if start >= end:
        return 0
    result = await db.execute(
        text(
            """
            INSERT INTO check_rollups_hourly
                (monitor_id, hour, checks, failures, avg_ms, p50_ms, p95_ms, p99_ms)
            SELECT
                monitor_id,
                date_trunc('hour', checked_at) AS hour,
                count(*),
                count(*) FILTER (WHERE NOT success),
                avg(latency_ms) FILTER (WHERE success AND latency_ms IS NOT NULL),
                percentile_cont(0.50) WITHIN GROUP (ORDER BY latency_ms)
                    FILTER (WHERE success AND latency_ms IS NOT NULL),
                percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)
                    FILTER (WHERE success AND latency_ms IS NOT NULL),
                percentile_cont(0.99) WITHIN GROUP (ORDER BY latency_ms)
                    FILTER (WHERE success AND latency_ms IS NOT NULL)
            FROM check_results
            WHERE checked_at >= :start AND checked_at < :end
            GROUP BY monitor_id, date_trunc('hour', checked_at)
            ON CONFLICT (monitor_id, hour) DO UPDATE SET
                checks = EXCLUDED.checks,
                failures = EXCLUDED.failures,
                avg_ms = EXCLUDED.avg_ms,
                p50_ms = EXCLUDED.p50_ms,
                p95_ms = EXCLUDED.p95_ms,
                p99_ms = EXCLUDED.p99_ms
            """
        ),
        {"start": start, "end": end},
    )
    await db.commit()
    return result.rowcount


@dataclass(frozen=True)
class Point:
    """Stats for one hour: from a rollup row (complete hour) or computed from raw results."""

    hour: datetime
    checks: int
    failures: int
    avg_ms: float | None
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None


async def load_points(
    db: AsyncSession, monitor_id: UUID, since: datetime, now: datetime
) -> list[Point]:
    """Hourly points from `since` to `now`: rollups for complete hours, raw for the current one."""
    start = hour_floor(since)
    current_hour = hour_floor(now)
    points: list[Point] = []

    rows = await db.execute(
        text(
            """
            SELECT hour, checks, failures, avg_ms, p50_ms, p95_ms, p99_ms
            FROM check_rollups_hourly
            WHERE monitor_id = :monitor_id AND hour >= :start AND hour < :current_hour
            """
        ),
        {"monitor_id": monitor_id, "start": start, "current_hour": current_hour},
    )
    seen = set()
    for row in rows:
        points.append(Point(*row))
        seen.add(row[0])

    # Complete hours the rollup job has not reached yet are computed from raw results, so
    # numbers are right even if the job is late. Rollup rows win when both exist.
    raw = await db.execute(
        text(
            """
            SELECT
                date_trunc('hour', checked_at) AS hour,
                count(*),
                count(*) FILTER (WHERE NOT success),
                avg(latency_ms) FILTER (WHERE success AND latency_ms IS NOT NULL),
                percentile_cont(0.50) WITHIN GROUP (ORDER BY latency_ms)
                    FILTER (WHERE success AND latency_ms IS NOT NULL),
                percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)
                    FILTER (WHERE success AND latency_ms IS NOT NULL),
                percentile_cont(0.99) WITHIN GROUP (ORDER BY latency_ms)
                    FILTER (WHERE success AND latency_ms IS NOT NULL)
            FROM check_results
            WHERE monitor_id = :monitor_id AND checked_at >= :start AND checked_at <= :now
            GROUP BY date_trunc('hour', checked_at)
            """
        ),
        {"monitor_id": monitor_id, "start": start, "now": now},
    )
    for row in raw:
        if row[0] not in seen:
            points.append(Point(*row))
    points.sort(key=lambda point: point.hour)
    return points


def _weighted(points: list[Point], field: str) -> float | None:
    """Check-weighted average of a latency figure. Approximate for percentiles."""
    pairs = [(getattr(p, field), p.checks - p.failures) for p in points]
    pairs = [(value, weight) for value, weight in pairs if value is not None and weight > 0]
    total = sum(weight for _, weight in pairs)
    if total == 0:
        return None
    return round(sum(value * weight for value, weight in pairs) / total, 1)


@dataclass(frozen=True)
class Summary:
    checks: int
    failures: int
    uptime_percent: float | None
    avg_ms: float | None
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None


def summarize(points: list[Point]) -> Summary:
    checks = sum(p.checks for p in points)
    failures = sum(p.failures for p in points)
    return Summary(
        checks=checks,
        failures=failures,
        uptime_percent=uptime_percent(checks, failures),
        avg_ms=_weighted(points, "avg_ms"),
        p50_ms=_weighted(points, "p50_ms"),
        p95_ms=_weighted(points, "p95_ms"),
        p99_ms=_weighted(points, "p99_ms"),
    )


def bucket_by_day(points: list[Point]) -> list[Point]:
    days: dict[datetime, list[Point]] = {}
    for point in points:
        day = point.hour.astimezone(UTC).replace(hour=0)
        days.setdefault(day, []).append(point)
    result = []
    for day, group in sorted(days.items()):
        s = summarize(group)
        result.append(Point(day, s.checks, s.failures, s.avg_ms, s.p50_ms, s.p95_ms, s.p99_ms))
    return result


def window_start(window: str, now: datetime) -> datetime:
    return now - WINDOWS[window]
