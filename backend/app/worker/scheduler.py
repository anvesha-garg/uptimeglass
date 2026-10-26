"""The scheduler: finds due monitors, checks them concurrently and records the results.

The monitors table is the job queue. A "claim" moves next_check_at forward, so no other
worker (or the next cycle) picks the same monitor up while it is being checked.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.alerts.dispatcher import dispatch_recorded
from app.models import Monitor
from app.services.checker import CheckOutcome, run_check
from app.services.results import RecordedCheck, record_check

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1.0
BATCH_SIZE = 50  # monitors claimed per cycle
MAX_CONCURRENT_CHECKS = 20  # checks running at the same time
LEASE_BUFFER_SECONDS = 30  # extra time a claim lasts after the check timeout

SessionFactory = async_sessionmaker[AsyncSession]


@dataclass(frozen=True)
class MonitorSnapshot:
    """The monitor fields a check needs. A plain copy, so no database object crosses sessions."""

    id: UUID
    url: str
    method: str
    timeout_seconds: int
    expected_status: int
    keyword: str | None


# Takes a snapshot and returns the check outcome. Tests pass a fake one.
Checker = Callable[[MonitorSnapshot], Awaitable[CheckOutcome]]
# Takes the session factory and a recorded check, and sends any alerts it calls for.
Notifier = Callable[[SessionFactory, RecordedCheck], Awaitable[object]]


async def default_checker(snapshot: MonitorSnapshot) -> CheckOutcome:
    return await run_check(
        snapshot.url,
        method=snapshot.method,
        timeout_seconds=snapshot.timeout_seconds,
        expected_status=snapshot.expected_status,
        keyword=snapshot.keyword,
    )


async def claim_due_monitors(
    db: AsyncSession, now: datetime, batch_size: int = BATCH_SIZE
) -> list[MonitorSnapshot]:
    """Lock due monitors, move their next_check_at forward, commit and return copies."""
    monitors = (
        await db.scalars(
            select(Monitor)
            # "NOT is_paused" matches the partial index on next_check_at.
            .where(~Monitor.is_paused, Monitor.next_check_at <= now)
            .order_by(Monitor.next_check_at)
            .limit(batch_size)
            # SKIP LOCKED: rows another worker holds are skipped instead of waited for.
            .with_for_update(skip_locked=True)
        )
    ).all()

    snapshots = []
    for monitor in monitors:
        snapshots.append(
            MonitorSnapshot(
                id=monitor.id,
                url=monitor.url,
                method=monitor.method,
                timeout_seconds=monitor.timeout_seconds,
                expected_status=monitor.expected_status,
                keyword=monitor.keyword,
            )
        )
        # The claim is a lease: if the worker dies, the monitor is due again after this.
        monitor.next_check_at = now + timedelta(
            seconds=monitor.timeout_seconds + LEASE_BUFFER_SECONDS
        )
    await db.commit()  # releases the row locks
    return snapshots


async def _check_and_record(
    session_factory: SessionFactory,
    snapshot: MonitorSnapshot,
    checker: Checker,
    notifier: Notifier,
    semaphore: asyncio.Semaphore,
    record_now: datetime | None,
) -> None:
    recorded = None
    async with semaphore:
        try:
            outcome = await checker(snapshot)
            # Each check saves with its own session, so concurrent checks never share one.
            async with session_factory() as db:
                recorded = await record_check(db, snapshot.id, outcome, now=record_now)
        except Exception:
            # One broken monitor must never stop the others. The lease makes it retry later.
            logger.exception("Check failed to complete for monitor %s", snapshot.id)
            return

    # Alerts are sent after the semaphore is released, so a slow webhook holds no check slot.
    if recorded is not None:
        try:
            await notifier(session_factory, recorded)
        except Exception:
            # An alert problem must never affect checking.
            logger.exception("Sending alerts failed for monitor %s", snapshot.id)


async def run_cycle(
    session_factory: SessionFactory,
    checker: Checker = default_checker,
    *,
    notifier: Notifier = dispatch_recorded,
    now: datetime | None = None,
    max_concurrent: int = MAX_CONCURRENT_CHECKS,
    batch_size: int = BATCH_SIZE,
) -> int:
    """Claim due monitors and check them all. Returns how many were claimed.

    "now" is for tests, which simulate the passing of time. Real runs leave it empty.
    """
    claim_time = now or datetime.now(UTC)
    async with session_factory() as db:
        claimed = await claim_due_monitors(db, claim_time, batch_size)
    if not claimed:
        return 0

    semaphore = asyncio.Semaphore(max_concurrent)
    await asyncio.gather(
        *(_check_and_record(session_factory, s, checker, notifier, semaphore, now) for s in claimed)
    )
    return len(claimed)


async def run_forever(
    session_factory: SessionFactory,
    stop_event: asyncio.Event,
    *,
    checker: Checker = default_checker,
    notifier: Notifier = dispatch_recorded,
    poll_interval: float = POLL_INTERVAL_SECONDS,
) -> None:
    """Run cycles until stop_event is set. Errors are logged and the loop keeps going."""
    while not stop_event.is_set():
        try:
            await run_cycle(session_factory, checker, notifier=notifier)
        except Exception:
            # For example the database is briefly down. Try again on the next round.
            logger.exception("Scheduler cycle failed")
        try:
            # Sleeps for the poll interval, but wakes up at once when asked to stop.
            await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
        except TimeoutError:
            pass
