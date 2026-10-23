from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select

from app.models import CheckResult, Incident, Monitor, User
from app.services.checker import CheckOutcome
from app.services.results import record_check

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
OK = CheckOutcome(success=True, status_code=200, latency_ms=50)
FAIL = CheckOutcome(
    success=False, status_code=503, latency_ms=70, error_type="status_code", error_detail="Got 503."
)


async def make_monitor(db, **overrides) -> Monitor:
    user = User(email=f"{uuid4()}@example.com", password_hash="x")
    db.add(user)
    await db.commit()
    values = {
        "user_id": user.id,
        "name": "Site",
        "url": "https://example.com",
        "status": "PENDING",
        "next_check_at": NOW,
    }
    values.update(overrides)
    monitor = Monitor(**values)
    db.add(monitor)
    await db.commit()
    return monitor


async def record(db, monitor, outcome, minute=0):
    return await record_check(db, monitor.id, outcome, now=NOW + timedelta(minutes=minute))


async def count(db, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


async def test_records_a_check_result_row(db_session):
    monitor = await make_monitor(db_session)
    recorded = await record(db_session, monitor, OK)
    assert recorded is not None

    row = await db_session.scalar(select(CheckResult))
    assert row.monitor_id == monitor.id
    assert row.success is True
    assert row.status_code == 200
    assert row.latency_ms == 50
    assert row.checked_at == NOW
    assert monitor.status == "UP"
    assert monitor.last_checked_at == NOW


async def test_outage_creates_exactly_one_incident_and_recovery_resolves_it(db_session):
    monitor = await make_monitor(db_session, status="UP")

    for minute in range(2):
        await record(db_session, monitor, FAIL, minute)
    assert await count(db_session, Incident) == 0  # two failures are not an outage yet

    third = await record(db_session, monitor, FAIL, 2)
    assert third.opened is not None
    assert monitor.status == "DOWN"
    assert await count(db_session, Incident) == 1

    await record(db_session, monitor, OK, 3)
    assert monitor.status == "DOWN"  # one success is not enough
    last = await record(db_session, monitor, OK, 4)
    assert monitor.status == "UP"
    assert last.resolved is not None

    incident = await db_session.scalar(select(Incident))
    assert await count(db_session, Incident) == 1
    assert incident.status == "resolved"
    assert incident.started_at == NOW + timedelta(minutes=2)
    assert incident.resolved_at == NOW + timedelta(minutes=4)
    assert await count(db_session, CheckResult) == 5


async def test_no_duplicate_incident_while_down(db_session):
    monitor = await make_monitor(db_session, status="UP")
    for minute in range(6):
        await record(db_session, monitor, FAIL, minute)
    assert monitor.status == "DOWN"
    assert await count(db_session, Incident) == 1


async def test_incident_records_cause_and_details(db_session):
    monitor = await make_monitor(db_session, status="UP")
    for minute in range(3):
        await record(db_session, monitor, FAIL, minute)

    incident = await db_session.scalar(select(Incident))
    assert incident.status == "open"
    assert incident.cause == "status_code"
    assert incident.details["status_code"] == 503
    assert incident.details["consecutive_failures"] == 3
    assert incident.resolved_at is None
    assert incident.ai_summary is None


async def test_paused_monitor_stores_the_result_but_does_not_change(db_session):
    monitor = await make_monitor(db_session, status="PAUSED", is_paused=True)
    for minute in range(5):
        await record(db_session, monitor, FAIL, minute)
    assert monitor.status == "PAUSED"
    assert await count(db_session, Incident) == 0
    assert await count(db_session, CheckResult) == 5


async def test_unknown_monitor_returns_none(db_session):
    assert await record_check(db_session, uuid4(), OK) is None


async def test_ssl_expiry_is_saved_on_the_monitor(db_session):
    monitor = await make_monitor(db_session)
    expires = datetime(2030, 6, 1, tzinfo=UTC)
    await record(db_session, monitor, CheckOutcome(success=True, ssl_expires_at=expires))
    assert monitor.ssl_expires_at == expires


async def test_leftover_open_incident_is_resolved_when_the_monitor_is_up_again(db_session):
    # Example: the user resumed or edited a monitor while its incident was still open.
    monitor = await make_monitor(db_session, status="PENDING")
    db_session.add(Incident(monitor_id=monitor.id, started_at=NOW, status="open", cause="timeout"))
    await db_session.commit()

    await record(db_session, monitor, OK, 1)
    incident = await db_session.scalar(select(Incident))
    assert incident.status == "resolved"
    assert monitor.status == "UP"


async def test_existing_open_incident_is_not_duplicated(db_session):
    monitor = await make_monitor(db_session, status="PENDING")
    db_session.add(Incident(monitor_id=monitor.id, started_at=NOW, status="open", cause="timeout"))
    await db_session.commit()

    for minute in range(3):
        await record(db_session, monitor, FAIL, minute)
    assert monitor.status == "DOWN"
    assert await count(db_session, Incident) == 1


async def test_deleting_a_monitor_deletes_its_history(db_session):
    monitor = await make_monitor(db_session, status="UP")
    for minute in range(3):
        await record(db_session, monitor, FAIL, minute)
    assert await count(db_session, CheckResult) == 3
    assert await count(db_session, Incident) == 1

    await db_session.delete(monitor)
    await db_session.commit()
    assert await count(db_session, CheckResult) == 0
    assert await count(db_session, Incident) == 0
