"""Roll up, then prune. Rollups are the only copy of old history, so they come first."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlertEvent, CheckResult, CheckRollupHourly, RefreshToken
from app.services.analytics import hour_floor, rollup_hours

logger = logging.getLogger(__name__)

RAW_RETENTION_DAYS = 30
ROLLUP_RETENTION_DAYS = 365
ALERT_EVENT_RETENTION_DAYS = 90
TOKEN_GRACE_DAYS = 1
ROLLUP_MARGIN_DAYS = 1  # re-roll a little more than we keep, to catch late results
LOCK_KEY = 726_001  # any constant; every worker uses the same one


@dataclass(frozen=True)
class RetentionReport:
    rolled_up: int
    raw_deleted: int
    rollups_deleted: int
    tokens_deleted: int
    events_deleted: int


async def run_retention(db: AsyncSession, now: datetime | None = None) -> RetentionReport:
    now = now or datetime.now(UTC)

    # 1. Roll up first. If this raises, nothing below runs and nothing is deleted.
    # Start from the oldest raw result, so everything the prune deletes has been rolled up,
    # even if the worker was off for a long time.
    oldest = await db.scalar(select(func.min(CheckResult.checked_at)))
    rollup_start = now - timedelta(days=RAW_RETENTION_DAYS + ROLLUP_MARGIN_DAYS)
    if oldest is not None:
        rollup_start = min(rollup_start, oldest)
    rolled_up = await rollup_hours(db, rollup_start, now)

    # 2. Prune raw results. The cutoff is a whole hour, so no hour is half-deleted.
    raw_cutoff = hour_floor(now - timedelta(days=RAW_RETENTION_DAYS))
    raw = await db.execute(delete(CheckResult).where(CheckResult.checked_at < raw_cutoff))

    rollups = await db.execute(
        delete(CheckRollupHourly).where(
            CheckRollupHourly.hour < now - timedelta(days=ROLLUP_RETENTION_DAYS)
        )
    )
    token_cutoff = now - timedelta(days=TOKEN_GRACE_DAYS)
    tokens = await db.execute(
        delete(RefreshToken).where(
            or_(RefreshToken.expires_at < token_cutoff, RefreshToken.revoked_at < token_cutoff)
        )
    )
    events = await db.execute(
        delete(AlertEvent).where(
            AlertEvent.sent_at < now - timedelta(days=ALERT_EVENT_RETENTION_DAYS)
        )
    )
    await db.commit()
    return RetentionReport(
        rolled_up=rolled_up,
        raw_deleted=raw.rowcount,
        rollups_deleted=rollups.rowcount,
        tokens_deleted=tokens.rowcount,
        events_deleted=events.rowcount,
    )


async def run_retention_locked(
    db: AsyncSession, now: datetime | None = None
) -> RetentionReport | None:
    """Runs retention unless another worker is already doing it. Returns None if skipped."""
    got_lock = await db.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY})
    if not got_lock:
        return None
    try:
        return await run_retention(db, now)
    finally:
        # Advisory locks belong to the connection, so unlock on the same session.
        await db.rollback()
        await db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
        await db.commit()
