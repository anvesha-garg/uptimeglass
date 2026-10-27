from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import CheckResult, Monitor

PASSWORD = "correct-horse-battery"


async def make_user_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def headers(client):
    return await make_user_headers(client, "owner@example.com")


@pytest.fixture
async def other_headers(client):
    return await make_user_headers(client, "other@example.com")


async def make_monitor(client, headers) -> str:
    response = await client.post(
        "/api/v1/monitors", json={"name": "Site", "url": "https://example.com"}, headers=headers
    )
    return response.json()["id"]


async def add_results(db, monitor_id: str, specs: list[tuple[timedelta, bool, int]]):
    monitor = await db.scalar(select(Monitor).where(Monitor.id == monitor_id))
    now = datetime.now(UTC)
    for ago, success, latency in specs:
        db.add(
            CheckResult(
                monitor_id=monitor.id,
                checked_at=now - ago,
                success=success,
                latency_ms=latency if success else None,
            )
        )
    await db.commit()


async def test_requires_login(client):
    zero = "00000000-0000-0000-0000-000000000000"
    assert (await client.get(f"/api/v1/monitors/{zero}/summary")).status_code == 401
    assert (await client.get(f"/api/v1/monitors/{zero}/timeseries")).status_code == 401


async def test_no_data_means_null_uptime_not_100(client, headers):
    monitor = await make_monitor(client, headers)
    data = (await client.get(f"/api/v1/monitors/{monitor}/summary", headers=headers)).json()
    assert data["checks"] == 0
    assert data["uptime_percent"] is None
    assert data["avg_ms"] is None
    assert data["status"] == "PENDING"


async def test_summary_reports_uptime_and_latency(client, headers, db_session):
    monitor = await make_monitor(client, headers)
    await add_results(
        db_session,
        monitor,
        [
            (timedelta(minutes=1), True, 100),
            (timedelta(minutes=2), True, 300),
            (timedelta(minutes=3), True, 200),
            (timedelta(minutes=4), False, 0),
        ],
    )
    data = (await client.get(f"/api/v1/monitors/{monitor}/summary", headers=headers)).json()
    assert (data["checks"], data["failures"]) == (4, 1)
    assert data["uptime_percent"] == 75.0
    assert data["avg_ms"] == 200
    assert data["window"] == "24h"


async def test_window_excludes_older_results(client, headers, db_session):
    monitor = await make_monitor(client, headers)
    await add_results(
        db_session,
        monitor,
        [(timedelta(minutes=1), True, 100), (timedelta(days=3), False, 0)],
    )
    day = (await client.get(f"/api/v1/monitors/{monitor}/summary", headers=headers)).json()
    week = (
        await client.get(f"/api/v1/monitors/{monitor}/summary?window=7d", headers=headers)
    ).json()
    assert day["checks"] == 1
    assert week["checks"] == 2


async def test_timeseries_hourly_and_daily(client, headers, db_session):
    monitor = await make_monitor(client, headers)
    await add_results(
        db_session,
        monitor,
        [(timedelta(minutes=1), True, 100), (timedelta(hours=5), True, 200)],
    )
    hourly = (
        await client.get(f"/api/v1/monitors/{monitor}/timeseries?window=24h", headers=headers)
    ).json()
    assert hourly["bucket"] == "hour"
    assert sum(point["checks"] for point in hourly["points"]) == 2
    assert [p["time"] for p in hourly["points"]] == sorted(p["time"] for p in hourly["points"])

    daily = (
        await client.get(
            f"/api/v1/monitors/{monitor}/timeseries?window=7d&bucket=day", headers=headers
        )
    ).json()
    assert daily["bucket"] == "day"
    assert sum(point["checks"] for point in daily["points"]) == 2


async def test_bad_parameters_are_rejected(client, headers):
    monitor = await make_monitor(client, headers)
    base = f"/api/v1/monitors/{monitor}"
    assert (await client.get(f"{base}/summary?window=1y", headers=headers)).status_code == 422
    assert (await client.get(f"{base}/timeseries?bucket=week", headers=headers)).status_code == 422


async def test_other_users_cannot_read_a_monitors_numbers(client, headers, other_headers):
    monitor = await make_monitor(client, headers)
    assert (
        await client.get(f"/api/v1/monitors/{monitor}/summary", headers=other_headers)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/monitors/{monitor}/timeseries", headers=other_headers)
    ).status_code == 404
