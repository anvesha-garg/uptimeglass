import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.alerts import dispatcher
from app.alerts.dispatcher import dispatch_recorded, ssl_threshold
from app.alerts.message import AlertSendError
from app.models import AlertChannel, AlertEvent, Monitor, MonitorAlertChannel, User
from app.services.checker import CheckOutcome
from app.services.results import record_check

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
OK = CheckOutcome(success=True, status_code=200, latency_ms=50)
FAIL = CheckOutcome(
    success=False, status_code=503, latency_ms=70, error_type="status_code", error_detail="Got 503."
)


@pytest.fixture
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def sent(monkeypatch) -> list[tuple]:
    """Replaces the real sender. Records (channel id, message) for every send."""
    calls: list[tuple] = []

    async def fake_send(channel, message):
        calls.append((channel.id, message))

    monkeypatch.setattr(dispatcher, "send_to_channel", fake_send)
    return calls


def kinds(calls) -> list[str]:
    return [message.kind for _, message in calls]


async def make_monitor(db, **overrides) -> tuple[User, Monitor]:
    user = User(email=f"{uuid4()}@example.com", password_hash="x")
    db.add(user)
    await db.commit()
    values = {
        "user_id": user.id,
        "name": "My site",
        "url": "https://example.com",
        "status": "UP",
        "next_check_at": NOW,
    }
    values.update(overrides)
    monitor = Monitor(**values)
    db.add(monitor)
    await db.commit()
    return user, monitor


async def add_channel(db, user, monitor, verified=True, linked=True) -> AlertChannel:
    channel = AlertChannel(
        user_id=user.id,
        type="webhook",
        config={"url": "https://hook.example.com/x", "secret": "s"},
        is_verified=verified,
    )
    db.add(channel)
    await db.commit()
    if linked:
        db.add(MonitorAlertChannel(monitor_id=monitor.id, channel_id=channel.id))
        await db.commit()
    return channel


async def go_down(db, monitor):
    """Three failures in a row. Returns the recorded check that opened the incident."""
    recorded = None
    for minute in range(3):
        recorded = await record_check(db, monitor.id, FAIL, now=NOW + timedelta(minutes=minute))
    return recorded


async def recover(db, monitor):
    """Two successes in a row. Returns the recorded check that resolved the incident."""
    await record_check(db, monitor.id, OK, now=NOW + timedelta(minutes=3))
    return await record_check(db, monitor.id, OK, now=NOW + timedelta(minutes=4))


async def all_events(db) -> list[AlertEvent]:
    # populate_existing: read the current rows, not objects the session saw earlier.
    result = await db.scalars(
        select(AlertEvent).order_by(AlertEvent.sent_at).execution_options(populate_existing=True)
    )
    return list(result)


# ---------- incident alerts ----------


async def test_opened_alert_goes_to_every_verified_linked_channel(
    db_session, session_factory, sent
):
    user, monitor = await make_monitor(db_session)
    first = await add_channel(db_session, user, monitor)
    second = await add_channel(db_session, user, monitor)
    await add_channel(db_session, user, monitor, verified=False)  # not verified: skipped
    await add_channel(db_session, user, monitor, linked=False)  # not linked: skipped

    recorded = await go_down(db_session, monitor)
    assert await dispatch_recorded(session_factory, recorded) == 2

    assert sorted((channel_id, m.kind) for channel_id, m in sent) == sorted(
        [(first.id, "opened"), (second.id, "opened")]
    )
    events = await all_events(db_session)
    assert len(events) == 2
    assert all(e.success and e.kind == "opened" for e in events)
    assert all(e.incident_id == recorded.opened.id for e in events)
    assert all(e.monitor_id == monitor.id for e in events)


async def test_the_same_alert_is_never_sent_twice(db_session, session_factory, sent):
    user, monitor = await make_monitor(db_session)
    await add_channel(db_session, user, monitor)
    recorded = await go_down(db_session, monitor)

    assert await dispatch_recorded(session_factory, recorded) == 1
    assert await dispatch_recorded(session_factory, recorded) == 0  # already handled
    assert len(sent) == 1
    assert len(await all_events(db_session)) == 1


async def test_ordinary_checks_send_nothing(db_session, session_factory, sent):
    user, monitor = await make_monitor(db_session)
    await add_channel(db_session, user, monitor)

    recorded = await record_check(db_session, monitor.id, OK, now=NOW)
    assert await dispatch_recorded(session_factory, recorded) == 0
    recorded = await record_check(db_session, monitor.id, FAIL, now=NOW)  # only one failure
    assert await dispatch_recorded(session_factory, recorded) == 0
    assert sent == []
    assert await all_events(db_session) == []


async def test_an_outage_sends_one_opened_and_one_resolved_alert(db_session, session_factory, sent):
    user, monitor = await make_monitor(db_session)
    channel = await add_channel(db_session, user, monitor)

    await dispatch_recorded(session_factory, await go_down(db_session, monitor))
    await dispatch_recorded(session_factory, await recover(db_session, monitor))

    assert [(c, k) for (c, _), k in zip(sent, kinds(sent), strict=True)] == [
        (channel.id, "opened"),
        (channel.id, "resolved"),
    ]
    events = await all_events(db_session)
    assert [e.kind for e in events] == ["opened", "resolved"]
    assert events[0].incident_id == events[1].incident_id


async def test_the_alert_text_describes_the_outage(db_session, session_factory, sent):
    user, monitor = await make_monitor(db_session)
    await add_channel(db_session, user, monitor)
    await dispatch_recorded(session_factory, await go_down(db_session, monitor))

    ((_, message),) = sent
    assert message.title == "My site is DOWN"
    assert "status_code" in message.text
    assert "Got 503." in message.text
    assert message.monitor_name == "My site"
    assert message.url == "https://example.com"
    assert message.monitor_id == str(monitor.id)


# ---------- failures never escape ----------


async def test_a_failing_channel_is_logged_and_does_not_stop_the_others(
    db_session, session_factory, monkeypatch
):
    user, monitor = await make_monitor(db_session)
    bad = await add_channel(db_session, user, monitor)
    good = await add_channel(db_session, user, monitor)
    delivered = []

    async def fake_send(channel, message):
        if channel.id == bad.id:
            raise AlertSendError("The webhook answered with status 500.")
        delivered.append(channel.id)

    monkeypatch.setattr(dispatcher, "send_to_channel", fake_send)
    recorded = await go_down(db_session, monitor)

    assert await dispatch_recorded(session_factory, recorded) == 2  # no exception escapes
    assert delivered == [good.id]
    by_channel = {e.channel_id: e for e in await all_events(db_session)}
    assert by_channel[bad.id].success is False
    assert by_channel[bad.id].error == "The webhook answered with status 500."
    assert by_channel[good.id].success is True
    assert by_channel[good.id].error is None


async def test_an_unexpected_crash_is_logged_without_leaking_details(
    db_session, session_factory, monkeypatch
):
    user, monitor = await make_monitor(db_session)
    await add_channel(db_session, user, monitor)

    async def crashing_send(channel, message):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(dispatcher, "send_to_channel", crashing_send)
    recorded = await go_down(db_session, monitor)

    assert await dispatch_recorded(session_factory, recorded) == 1
    (event,) = await all_events(db_session)
    assert event.success is False
    assert event.error == "Unexpected error while sending."
    assert "secret" not in event.error


async def test_a_slow_send_is_cut_off(db_session, session_factory, monkeypatch):
    user, monitor = await make_monitor(db_session)
    await add_channel(db_session, user, monitor)

    async def slow_send(channel, message):
        await asyncio.sleep(2)

    monkeypatch.setattr(dispatcher, "send_to_channel", slow_send)
    monkeypatch.setattr(dispatcher, "SEND_TIMEOUT_SECONDS", 0.05)
    recorded = await go_down(db_session, monitor)

    await dispatch_recorded(session_factory, recorded)
    (event,) = await all_events(db_session)
    assert event.success is False
    assert event.error == "The alert took too long to send."


async def test_a_failed_alert_is_not_sent_again(db_session, session_factory, monkeypatch):
    user, monitor = await make_monitor(db_session)
    await add_channel(db_session, user, monitor)
    attempts = []

    async def failing_send(channel, message):
        attempts.append(1)
        raise AlertSendError("down")

    monkeypatch.setattr(dispatcher, "send_to_channel", failing_send)
    recorded = await go_down(db_session, monitor)

    await dispatch_recorded(session_factory, recorded)
    await dispatch_recorded(session_factory, recorded)
    assert len(attempts) == 1  # no repeats, even after a failure
    assert len(await all_events(db_session)) == 1


# ---------- SSL expiry warnings ----------


@pytest.mark.parametrize(
    ("days_left", "expected"),
    [(31, None), (30, 30), (15, 30), (14, 14), (8, 14), (7, 7), (0, 7), (-5, 7)],
)
def test_ssl_threshold(days_left, expected):
    assert ssl_threshold(days_left) == expected


async def test_ssl_warnings_are_sent_once_per_threshold(db_session, session_factory, sent):
    user, monitor = await make_monitor(db_session)
    await add_channel(db_session, user, monitor)
    expires = NOW + timedelta(days=30, hours=1)
    recorded = await record_check(
        db_session, monitor.id, CheckOutcome(success=True, ssl_expires_at=expires), now=NOW
    )

    async def day(number: int) -> int:
        return await dispatch_recorded(session_factory, recorded, now=NOW + timedelta(days=number))

    assert await day(-10) == 0  # 40 days left: far away
    assert await day(0) == 1  # 30 days left: first warning
    assert await day(1) == 0  # 29 days left: same threshold, already sent
    assert await day(16) == 1  # 14 days left
    assert await day(17) == 0
    assert await day(23) == 1  # 7 days left
    assert await day(25) == 0
    assert kinds(sent) == ["ssl_expiry"] * 3
    events = await all_events(db_session)
    assert all(e.incident_id is None and e.monitor_id == monitor.id for e in events)


async def test_an_expired_certificate_is_reported_as_expired(db_session, session_factory, sent):
    user, monitor = await make_monitor(db_session)
    await add_channel(db_session, user, monitor)
    expired = NOW - timedelta(days=2)
    recorded = await record_check(
        db_session, monitor.id, CheckOutcome(success=True, ssl_expires_at=expired), now=NOW
    )

    assert await dispatch_recorded(session_factory, recorded, now=NOW) == 1
    assert "expired" in sent[0][1].text


async def test_no_ssl_warning_after_a_failed_check(db_session, session_factory, sent):
    # The stored expiry date may be old, so only a successful check is trusted.
    user, monitor = await make_monitor(db_session, ssl_expires_at=NOW + timedelta(days=2))
    await add_channel(db_session, user, monitor)

    recorded = await record_check(db_session, monitor.id, FAIL, now=NOW)
    assert await dispatch_recorded(session_factory, recorded, now=NOW) == 0
    assert sent == []


# ---------- cleanup ----------


async def test_deleting_a_channel_deletes_its_events(db_session, session_factory, sent):
    user, monitor = await make_monitor(db_session)
    channel = await add_channel(db_session, user, monitor)
    await dispatch_recorded(session_factory, await go_down(db_session, monitor))
    assert len(await all_events(db_session)) == 1

    await db_session.delete(channel)
    await db_session.commit()
    assert await all_events(db_session) == []


async def test_deleting_a_monitor_deletes_its_events(db_session, session_factory, sent):
    user, monitor = await make_monitor(db_session)
    await add_channel(db_session, user, monitor)
    await dispatch_recorded(session_factory, await go_down(db_session, monitor))

    await db_session.delete(monitor)
    await db_session.commit()
    assert await all_events(db_session) == []
