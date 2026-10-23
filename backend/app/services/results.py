"""Saves one check result and applies its effects: monitor state and incidents."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CheckResult, Incident, Monitor
from app.services.checker import CheckOutcome
from app.services.state_machine import Transition, apply_outcome


@dataclass(frozen=True)
class RecordedCheck:
    result: CheckResult
    transition: Transition
    opened: Incident | None  # set only when this check opened an incident
    resolved: Incident | None  # set only when this check resolved one


async def _open_incident(db: AsyncSession, monitor_id: UUID) -> Incident | None:
    return await db.scalar(
        select(Incident).where(Incident.monitor_id == monitor_id, Incident.status == "open")
    )


async def record_check(
    db: AsyncSession, monitor_id: UUID, outcome: CheckOutcome, now: datetime | None = None
) -> RecordedCheck | None:
    """Store the result, update the monitor, open or resolve an incident, then commit.

    Returns None if the monitor was deleted while its check was running.
    """
    now = now or datetime.now(UTC)
    # FOR UPDATE: two results for the same monitor cannot change its counters at the same time.
    # populate_existing: always read fresh values, even if this session saw the row before.
    monitor = await db.scalar(
        select(Monitor)
        .where(Monitor.id == monitor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if monitor is None:
        await db.rollback()
        return None

    transition = apply_outcome(monitor, outcome, now)
    result = CheckResult(
        monitor_id=monitor.id,
        checked_at=now,
        success=outcome.success,
        status_code=outcome.status_code,
        latency_ms=outcome.latency_ms,
        error_type=outcome.error_type,
        error_detail=outcome.error_detail,
    )
    db.add(result)

    opened = None
    resolved = None
    if transition.went_down and await _open_incident(db, monitor.id) is None:
        # The check above also protects against a leftover open incident from before.
        opened = Incident(
            monitor_id=monitor.id,
            started_at=now,
            status="open",
            cause=outcome.error_type or "unknown",
            details={
                "error_type": outcome.error_type,
                "error_detail": outcome.error_detail,
                "status_code": outcome.status_code,
                "latency_ms": outcome.latency_ms,
                "consecutive_failures": monitor.consecutive_failures,
            },
        )
        db.add(opened)
    if transition.recovered:
        resolved = await _open_incident(db, monitor.id)
        if resolved is not None:
            resolved.status = "resolved"
            resolved.resolved_at = now

    await db.commit()
    return RecordedCheck(result=result, transition=transition, opened=opened, resolved=resolved)
