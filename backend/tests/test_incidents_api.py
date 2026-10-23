from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.models import Incident

PASSWORD = "correct-horse-battery"
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


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


async def create_monitor(client, headers) -> str:
    response = await client.post(
        "/api/v1/monitors", json={"name": "Site", "url": "https://example.com"}, headers=headers
    )
    return response.json()["id"]


async def add_incident(db, monitor_id: str, status="open", cause="timeout"):
    db.add(
        Incident(
            monitor_id=UUID(monitor_id),
            started_at=NOW,
            resolved_at=None if status == "open" else NOW,
            status=status,
            cause=cause,
            details={"error_type": cause},
        )
    )
    await db.commit()


async def test_incidents_require_login(client):
    assert (await client.get("/api/v1/incidents")).status_code == 401


async def test_lists_only_own_incidents(client, db_session, headers, other_headers):
    mine = await create_monitor(client, headers)
    theirs = await create_monitor(client, other_headers)
    await add_incident(db_session, mine)
    await add_incident(db_session, theirs)

    data = (await client.get("/api/v1/incidents", headers=headers)).json()
    assert data["total"] == 1
    assert data["items"][0]["monitor_id"] == mine
    assert data["items"][0]["cause"] == "timeout"
    assert data["items"][0]["details"] == {"error_type": "timeout"}


async def test_filter_by_status(client, db_session, headers):
    monitor = await create_monitor(client, headers)
    await add_incident(db_session, monitor, status="open")
    await add_incident(db_session, monitor, status="resolved")

    open_only = (await client.get("/api/v1/incidents?status=open", headers=headers)).json()
    assert [item["status"] for item in open_only["items"]] == ["open"]
    resolved = (await client.get("/api/v1/incidents?status=resolved", headers=headers)).json()
    assert [item["status"] for item in resolved["items"]] == ["resolved"]


async def test_filter_by_monitor(client, db_session, headers):
    first = await create_monitor(client, headers)
    second = await create_monitor(client, headers)
    await add_incident(db_session, first)
    await add_incident(db_session, second)

    data = (await client.get(f"/api/v1/incidents?monitor_id={first}", headers=headers)).json()
    assert data["total"] == 1
    assert data["items"][0]["monitor_id"] == first


async def test_paging(client, db_session, headers):
    monitor = await create_monitor(client, headers)
    await add_incident(db_session, monitor, status="resolved")
    await add_incident(db_session, monitor, status="open")

    page = (await client.get("/api/v1/incidents?limit=1&offset=1", headers=headers)).json()
    assert page["total"] == 2
    assert len(page["items"]) == 1


async def test_bad_filters_are_rejected(client, headers):
    assert (await client.get("/api/v1/incidents?status=nope", headers=headers)).status_code == 422
    assert (await client.get("/api/v1/incidents?limit=0", headers=headers)).status_code == 422
