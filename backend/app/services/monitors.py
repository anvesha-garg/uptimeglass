"""Monitor business rules: URL safety, plan limits, ownership."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import Monitor, User
from app.services.ssrf import UrlNotAllowed, validate_url

MAX_MONITORS_PER_USER = 20


async def check_url_is_safe(url: str) -> None:
    try:
        await validate_url(url)
    except UrlNotAllowed as error:
        raise AppError(422, "invalid_url", str(error)) from None


async def get_owned_monitor(db: AsyncSession, user: User, monitor_id: UUID) -> Monitor:
    """Load a monitor only if it belongs to the user. Someone else's monitor looks missing."""
    monitor = await db.scalar(
        select(Monitor).where(Monitor.id == monitor_id, Monitor.user_id == user.id)
    )
    if monitor is None:
        raise AppError(404, "not_found", "Monitor not found.")
    return monitor


def check_timeout_below_interval(timeout_seconds: int, interval_seconds: int) -> None:
    if timeout_seconds >= interval_seconds:
        raise AppError(
            422, "validation_error", "timeout_seconds must be less than interval_seconds"
        )


def check_keyword_needs_get(method: str, keyword: str | None) -> None:
    if method == "HEAD" and keyword is not None:
        raise AppError(
            422,
            "validation_error",
            "keyword checks need method GET, because HEAD responses have no body",
        )


async def create_monitor(db: AsyncSession, user: User, data: dict) -> Monitor:
    await check_url_is_safe(data["url"])

    # Lock the user row, so two simultaneous creates cannot both pass the limit check.
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    count = await db.scalar(
        select(func.count()).select_from(Monitor).where(Monitor.user_id == user.id)
    )
    if count >= MAX_MONITORS_PER_USER:
        raise AppError(
            409,
            "monitor_limit_reached",
            f"You can have at most {MAX_MONITORS_PER_USER} monitors.",
        )

    monitor = Monitor(
        user_id=user.id,
        status="PENDING",
        # Due immediately, so the scheduler (Phase 3) checks it right away.
        next_check_at=datetime.now(UTC),
        **data,
    )
    db.add(monitor)
    await db.commit()
    await db.refresh(monitor)
    return monitor


async def update_monitor(db: AsyncSession, monitor: Monitor, changes: dict) -> Monitor:
    # Cheap rules first, using the new values merged with the stored ones.
    interval = changes.get("interval_seconds", monitor.interval_seconds)
    timeout = changes.get("timeout_seconds", monitor.timeout_seconds)
    check_timeout_below_interval(timeout, interval)
    method = changes.get("method", monitor.method)
    keyword = changes["keyword"] if "keyword" in changes else monitor.keyword
    check_keyword_needs_get(method, keyword)

    if "url" in changes and changes["url"] != monitor.url:
        await check_url_is_safe(changes["url"])
        # Old results belong to the old URL, so start fresh.
        monitor.status = "PAUSED" if monitor.is_paused else "PENDING"
        monitor.consecutive_failures = 0
        monitor.consecutive_successes = 0
        monitor.ssl_expires_at = None
        monitor.last_checked_at = None
        monitor.next_check_at = datetime.now(UTC)

    for field, value in changes.items():
        setattr(monitor, field, value)
    await db.commit()
    await db.refresh(monitor)
    return monitor


async def pause_monitor(db: AsyncSession, monitor: Monitor) -> Monitor:
    monitor.is_paused = True
    monitor.status = "PAUSED"
    await db.commit()
    await db.refresh(monitor)
    return monitor


async def resume_monitor(db: AsyncSession, monitor: Monitor) -> Monitor:
    monitor.is_paused = False
    monitor.status = "PENDING"
    monitor.consecutive_failures = 0
    monitor.consecutive_successes = 0
    monitor.next_check_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(monitor)
    return monitor
