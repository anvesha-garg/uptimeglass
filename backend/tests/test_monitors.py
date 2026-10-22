from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Monitor
from app.services.monitors import MAX_MONITORS_PER_USER

PASSWORD = "correct-horse-battery"


async def make_user_headers(client, email: str) -> dict:
    """Registers and logs in a user, returns the Authorization header."""
    await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def headers(client):
    return await make_user_headers(client, "owner@example.com")


@pytest.fixture
async def other_headers(client):
    return await make_user_headers(client, "other@example.com")


def body(**overrides) -> dict:
    data = {"name": "My site", "url": "https://example.com"}
    data.update(overrides)
    return data


async def create(client, headers, **overrides):
    return await client.post("/api/v1/monitors", json=body(**overrides), headers=headers)


# ---------- create ----------


async def test_create_monitor_sets_defaults(client, headers):
    response = await create(client, headers)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "PENDING"
    assert data["is_paused"] is False
    assert data["method"] == "GET"
    assert data["interval_seconds"] == 300
    assert data["timeout_seconds"] == 10
    assert data["expected_status"] == 200
    assert data["keyword"] is None
    assert data["consecutive_failures"] == 0


async def test_new_monitor_is_due_immediately(client, headers, db_session):
    await create(client, headers)
    monitor = await db_session.scalar(select(Monitor))
    assert monitor.next_check_at <= datetime.now(UTC)


async def test_create_requires_login(client):
    response = await client.post("/api/v1/monitors", json=body())
    assert response.status_code == 401


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:8000/",
        "http://localhost/",
        "http://internal.example.com/",
        "ftp://example.com",
        "http://user:pass@example.com",
    ],
)
async def test_unsafe_urls_are_rejected(client, headers, url):
    response = await create(client, headers, url=url)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_url"


@pytest.mark.parametrize(
    "overrides",
    [
        {"interval_seconds": 59},  # below the 60s minimum
        {"interval_seconds": 86401},
        {"timeout_seconds": 0},
        {"timeout_seconds": 61},
        {"interval_seconds": 60, "timeout_seconds": 60},  # timeout must be below interval
        {"method": "POST"},
        {"expected_status": 99},
        {"expected_status": 600},
        {"name": ""},
        {"keyword": ""},
    ],
)
async def test_invalid_fields_are_rejected(client, headers, overrides):
    response = await create(client, headers, **overrides)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_monitor_limit_is_enforced(client, headers):
    for number in range(MAX_MONITORS_PER_USER):
        assert (await create(client, headers, name=f"Site {number}")).status_code == 201
    response = await create(client, headers, name="One too many")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "monitor_limit_reached"


async def test_limit_is_per_user(client, headers, other_headers):
    for number in range(MAX_MONITORS_PER_USER):
        await create(client, headers, name=f"Site {number}")
    # The other user is not affected by the first user's monitors.
    assert (await create(client, other_headers)).status_code == 201


# ---------- list and get ----------


async def test_list_returns_only_own_monitors_with_paging(client, headers, other_headers):
    for number in range(3):
        await create(client, headers, name=f"Mine {number}")
    await create(client, other_headers, name="Not mine")

    response = await client.get("/api/v1/monitors", headers=headers)
    data = response.json()
    assert data["total"] == 3
    assert {item["name"] for item in data["items"]} == {"Mine 0", "Mine 1", "Mine 2"}

    page = await client.get("/api/v1/monitors?limit=2&offset=2", headers=headers)
    assert len(page.json()["items"]) == 1
    assert page.json()["total"] == 3


async def test_list_rejects_bad_paging(client, headers):
    assert (await client.get("/api/v1/monitors?limit=0", headers=headers)).status_code == 422
    assert (await client.get("/api/v1/monitors?limit=101", headers=headers)).status_code == 422
    assert (await client.get("/api/v1/monitors?offset=-1", headers=headers)).status_code == 422


async def test_get_one_monitor(client, headers):
    created = (await create(client, headers)).json()
    response = await client.get(f"/api/v1/monitors/{created['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_unknown_id_returns_404(client, headers):
    response = await client.get(
        "/api/v1/monitors/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert response.status_code == 404


async def test_malformed_id_returns_422(client, headers):
    response = await client.get("/api/v1/monitors/not-a-uuid", headers=headers)
    assert response.status_code == 422


# ---------- ownership ----------


async def test_other_users_cannot_touch_a_monitor(client, headers, other_headers):
    monitor_id = (await create(client, headers)).json()["id"]
    url = f"/api/v1/monitors/{monitor_id}"

    # Every action on someone else's monitor looks like "not found".
    assert (await client.get(url, headers=other_headers)).status_code == 404
    assert (await client.patch(url, json={"name": "x"}, headers=other_headers)).status_code == 404
    assert (await client.delete(url, headers=other_headers)).status_code == 404
    assert (await client.post(f"{url}/pause", headers=other_headers)).status_code == 404
    assert (await client.post(f"{url}/resume", headers=other_headers)).status_code == 404

    # And nothing changed for the real owner.
    still_there = await client.get(url, headers=headers)
    assert still_there.status_code == 200
    assert still_there.json()["name"] == "My site"


# ---------- update ----------


async def test_patch_changes_only_the_sent_fields(client, headers):
    monitor_id = (await create(client, headers, keyword="hello")).json()["id"]
    response = await client.patch(
        f"/api/v1/monitors/{monitor_id}", json={"name": "Renamed"}, headers=headers
    )
    data = response.json()
    assert response.status_code == 200
    assert data["name"] == "Renamed"
    assert data["url"] == "https://example.com"
    assert data["keyword"] == "hello"


async def test_patch_can_remove_the_keyword(client, headers):
    monitor_id = (await create(client, headers, keyword="hello")).json()["id"]
    response = await client.patch(
        f"/api/v1/monitors/{monitor_id}", json={"keyword": None}, headers=headers
    )
    assert response.json()["keyword"] is None


async def test_patch_url_is_checked_and_resets_state(client, headers, db_session):
    monitor_id = (await create(client, headers)).json()["id"]

    bad = await client.patch(
        f"/api/v1/monitors/{monitor_id}",
        json={"url": "http://169.254.169.254/"},
        headers=headers,
    )
    assert bad.status_code == 422

    # Pretend the monitor was DOWN, then change its URL.
    monitor = await db_session.scalar(select(Monitor))
    monitor.status = "DOWN"
    monitor.consecutive_failures = 3
    monitor.ssl_expires_at = datetime.now(UTC) + timedelta(days=5)
    await db_session.commit()

    good = await client.patch(
        f"/api/v1/monitors/{monitor_id}",
        json={"url": "https://other.example.com"},
        headers=headers,
    )
    data = good.json()
    assert good.status_code == 200
    assert data["url"] == "https://other.example.com"
    assert data["status"] == "PENDING"
    assert data["consecutive_failures"] == 0
    assert data["ssl_expires_at"] is None


async def test_patch_checks_timeout_against_the_stored_interval(client, headers):
    created = await create(client, headers, interval_seconds=120, timeout_seconds=10)
    url = f"/api/v1/monitors/{created.json()['id']}"
    # Lowering only the interval below the stored timeout is invalid.
    both = {"interval_seconds": 60, "timeout_seconds": 60}
    assert (await client.patch(url, json=both, headers=headers)).status_code == 422
    too_long = {"timeout_seconds": 120}
    assert (await client.patch(url, json=too_long, headers=headers)).status_code == 422
    fine = {"timeout_seconds": 30}
    assert (await client.patch(url, json=fine, headers=headers)).status_code == 200


# ---------- delete, pause, resume ----------


async def test_delete_removes_the_monitor(client, headers):
    monitor_id = (await create(client, headers)).json()["id"]
    url = f"/api/v1/monitors/{monitor_id}"
    assert (await client.delete(url, headers=headers)).status_code == 204
    assert (await client.get(url, headers=headers)).status_code == 404


async def test_pause_and_resume(client, headers):
    monitor_id = (await create(client, headers)).json()["id"]
    url = f"/api/v1/monitors/{monitor_id}"

    paused = (await client.post(f"{url}/pause", headers=headers)).json()
    assert paused["is_paused"] is True
    assert paused["status"] == "PAUSED"

    resumed = (await client.post(f"{url}/resume", headers=headers)).json()
    assert resumed["is_paused"] is False
    assert resumed["status"] == "PENDING"


async def test_changing_the_url_of_a_paused_monitor_keeps_it_paused(client, headers):
    monitor_id = (await create(client, headers)).json()["id"]
    url = f"/api/v1/monitors/{monitor_id}"
    await client.post(f"{url}/pause", headers=headers)

    response = await client.patch(url, json={"url": "https://other.example.com"}, headers=headers)
    assert response.json()["status"] == "PAUSED"
    assert response.json()["is_paused"] is True
