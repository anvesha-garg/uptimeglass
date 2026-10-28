from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select

from app.models import CheckResult, Incident, Monitor, User
from app.services.anomaly import MIN_HISTORY, SLOW_STREAK
from app.services.checker import CheckOutcome
from app.services.results import record_check

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def ok(latency: int) -> CheckOutcome:
    return CheckOutcome(success=True, status_code=200, latency_ms=latency)


FAIL = CheckOutcome(success=False, error_type="timeout", error_detail="No answer.")


async def make_monitor(db, history: int = MIN_HISTORY) -> Monitor:
    """A monitor that already has `history` normal checks (about 100 ms) saved."""
    user = User(email=f"{uuid4()}@example.com", password_hash="x")
    db.add(user)
    await db.commit()
    monitor = Monitor(
        user_id=user.id, name="S", url="https://example.com", status="UP", next_check_at=NOW
    )
    db.add(monitor)
    await db.commit()
    for i in range(history):
        db.add(
            CheckResult(
                monitor_id=monitor.id,
                checked_at=NOW - timedelta(minutes=history - i),
                success=True,
                latency_ms=100 + (i % 3),
            )
        )
    await db.commit()
    return monitor


async def record(db, monitor, outcome, minute=0):
    return await record_check(db, monitor.id, outcome, now=NOW + timedelta(minutes=minute))


async def incidents(db) -> int:
    return await db.scalar(select(func.count()).select_from(Incident))


async def test_three_slow_checks_in_a_row_make_the_monitor_degraded(db_session):
    monitor = await make_monitor(db_session)
    for minute in range(SLOW_STREAK - 1):
        await record(db_session, monitor, ok(900), minute)
        assert monitor.status == "UP"  # one or two slow checks are not enough
    await record(db_session, monitor, ok(900), SLOW_STREAK)
    assert monitor.status == "DEGRADED"
    assert monitor.consecutive_slow == SLOW_STREAK


async def test_degraded_never_opens_an_incident_or_sends_alerts(db_session):
    monitor = await make_monitor(db_session)
    last = None
    for minute in range(5):
        last = await record(db_session, monitor, ok(900), minute)
    assert monitor.status == "DEGRADED"
    assert last.opened is None and last.resolved is None
    assert last.transition.went_down is False
    assert await incidents(db_session) == 0


async def test_one_normal_check_ends_degraded(db_session):
    monitor = await make_monitor(db_session)
    for minute in range(SLOW_STREAK):
        await record(db_session, monitor, ok(900), minute)
    assert monitor.status == "DEGRADED"

    await record(db_session, monitor, ok(101), 10)
    assert monitor.status == "UP"
    assert monitor.consecutive_slow == 0


async def test_a_normal_check_in_between_resets_the_streak(db_session):
    monitor = await make_monitor(db_session)
    await record(db_session, monitor, ok(900), 0)
    await record(db_session, monitor, ok(900), 1)
    await record(db_session, monitor, ok(101), 2)  # back to normal
    await record(db_session, monitor, ok(900), 3)
    await record(db_session, monitor, ok(900), 4)
    assert monitor.status == "UP"


async def test_no_history_means_no_degraded(db_session):
    monitor = await make_monitor(db_session, history=MIN_HISTORY - 1)
    # Only SLOW_STREAK - 1 checks: the first one is judged with too little history, and the
    # streak can never reach the threshold, so the monitor must stay UP.
    for minute in range(SLOW_STREAK - 1):
        await record(db_session, monitor, ok(5_000), minute)
    assert monitor.status == "UP"
    assert monitor.consecutive_slow < SLOW_STREAK


async def test_a_failure_while_degraded_still_leads_to_down_and_one_incident(db_session):
    monitor = await make_monitor(db_session)
    for minute in range(SLOW_STREAK):
        await record(db_session, monitor, ok(900), minute)
    assert monitor.status == "DEGRADED"

    for minute in range(10, 13):
        await record(db_session, monitor, FAIL, minute)
    assert monitor.status == "DOWN"
    assert monitor.consecutive_slow == 0
    assert await incidents(db_session) == 1


async def test_recovering_from_down_resolves_the_incident(db_session):
    monitor = await make_monitor(db_session)
    for minute in range(3):
        await record(db_session, monitor, FAIL, minute)
    await record(db_session, monitor, ok(101), 3)
    last = await record(db_session, monitor, ok(101), 4)
    assert monitor.status == "UP"
    assert last.resolved is not None


async def test_failed_checks_do_not_enter_the_baseline(db_session):
    monitor = await make_monitor(db_session)
    await record(db_session, monitor, FAIL, 0)  # no latency, must not break the next check
    await record(db_session, monitor, ok(101), 1)
    assert monitor.status == "UP"
    assert monitor.consecutive_slow == 0
