"""Uptime and latency numbers for one monitor."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.analytics import Bucket, PointOut, SummaryOut, TimeseriesOut, Window
from app.services import analytics as service
from app.services.monitors import get_owned_monitor

router = APIRouter(prefix="/monitors", tags=["analytics"])


@router.get("/{monitor_id}/summary", response_model=SummaryOut)
async def summary(monitor_id: UUID, user: CurrentUser, db: DbSession, window: Window = "24h"):
    monitor = await get_owned_monitor(db, user, monitor_id)
    now = datetime.now(UTC)
    points = await service.load_points(db, monitor.id, service.window_start(window, now), now)
    s = service.summarize(points)
    return SummaryOut(window=window, status=monitor.status, **s.__dict__)


@router.get("/{monitor_id}/timeseries", response_model=TimeseriesOut)
async def timeseries(
    monitor_id: UUID,
    user: CurrentUser,
    db: DbSession,
    window: Window = "24h",
    bucket: Bucket = "hour",
):
    monitor = await get_owned_monitor(db, user, monitor_id)
    now = datetime.now(UTC)
    points = await service.load_points(db, monitor.id, service.window_start(window, now), now)
    if bucket == "day":
        points = service.bucket_by_day(points)
    return TimeseriesOut(
        window=window,
        bucket=bucket,
        points=[
            PointOut(
                time=p.hour,
                checks=p.checks,
                failures=p.failures,
                uptime_percent=service.uptime_percent(p.checks, p.failures),
                avg_ms=None if p.avg_ms is None else round(p.avg_ms, 1),
                p95_ms=None if p.p95_ms is None else round(p.p95_ms, 1),
            )
            for p in points
        ],
    )
