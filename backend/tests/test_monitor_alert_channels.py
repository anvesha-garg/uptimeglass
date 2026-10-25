from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import MonitorAlertChannel

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


async def make_channel(client, headers, address: str) -> str:
    response = await client.post(
        "/api/v1/alert-channels", json={"type": "email", "address": address}, headers=headers
    )
    return response.json()["id"]


async def link_count(db) -> int:
    return await db.scalar(select(func.count()).select_from(MonitorAlertChannel))


def channels_url(monitor_id: str) -> str:
    return f"/api/v1/monitors/{monitor_id}/alert-channels"


async def test_requires_login(client):
    url = channels_url(str(uuid4()))
    assert (await client.get(url)).status_code == 401
    assert (await client.put(url, json={"channel_ids": []})).status_code == 401


async def test_set_and_get_channels(client, headers):
    monitor = await make_monitor(client, headers)
    first = await make_channel(client, headers, "a@example.com")
    second = await make_channel(client, headers, "b@example.com")

    response = await client.put(
        channels_url(monitor), json={"channel_ids": [first, second]}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["total"] == 2

    listing = (await client.get(channels_url(monitor), headers=headers)).json()
    assert [item["id"] for item in listing["items"]] == [first, second]


async def test_setting_channels_replaces_the_old_set(client, headers):
    monitor = await make_monitor(client, headers)
    first = await make_channel(client, headers, "a@example.com")
    second = await make_channel(client, headers, "b@example.com")

    await client.put(channels_url(monitor), json={"channel_ids": [first]}, headers=headers)
    await client.put(channels_url(monitor), json={"channel_ids": [second]}, headers=headers)

    listing = (await client.get(channels_url(monitor), headers=headers)).json()
    assert [item["id"] for item in listing["items"]] == [second]


async def test_empty_list_clears_the_channels(client, headers, db_session):
    monitor = await make_monitor(client, headers)
    channel = await make_channel(client, headers, "a@example.com")
    await client.put(channels_url(monitor), json={"channel_ids": [channel]}, headers=headers)

    response = await client.put(channels_url(monitor), json={"channel_ids": []}, headers=headers)
    assert response.json()["total"] == 0
    assert await link_count(db_session) == 0


async def test_duplicate_ids_are_linked_once(client, headers, db_session):
    monitor = await make_monitor(client, headers)
    channel = await make_channel(client, headers, "a@example.com")

    response = await client.put(
        channels_url(monitor), json={"channel_ids": [channel, channel]}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert await link_count(db_session) == 1


async def test_a_foreign_or_unknown_channel_changes_nothing(client, headers, other_headers):
    monitor = await make_monitor(client, headers)
    mine = await make_channel(client, headers, "a@example.com")
    theirs = await make_channel(client, other_headers, "b@example.com")
    await client.put(channels_url(monitor), json={"channel_ids": [mine]}, headers=headers)

    for bad_id in (theirs, str(uuid4())):
        response = await client.put(
            channels_url(monitor), json={"channel_ids": [mine, bad_id]}, headers=headers
        )
        assert response.status_code == 404

    # The earlier set is untouched.
    listing = (await client.get(channels_url(monitor), headers=headers)).json()
    assert [item["id"] for item in listing["items"]] == [mine]


async def test_other_users_cannot_see_or_change_a_monitors_channels(client, headers, other_headers):
    monitor = await make_monitor(client, headers)
    theirs = await make_channel(client, other_headers, "b@example.com")

    assert (await client.get(channels_url(monitor), headers=other_headers)).status_code == 404
    response = await client.put(
        channels_url(monitor), json={"channel_ids": [theirs]}, headers=other_headers
    )
    assert response.status_code == 404


async def test_too_many_ids_are_rejected(client, headers):
    monitor = await make_monitor(client, headers)
    ids = [str(uuid4()) for _ in range(11)]
    response = await client.put(channels_url(monitor), json={"channel_ids": ids}, headers=headers)
    assert response.status_code == 422


async def test_deleting_a_channel_removes_its_links(client, headers, db_session):
    monitor = await make_monitor(client, headers)
    channel = await make_channel(client, headers, "a@example.com")
    await client.put(channels_url(monitor), json={"channel_ids": [channel]}, headers=headers)
    assert await link_count(db_session) == 1

    await client.delete(f"/api/v1/alert-channels/{channel}", headers=headers)
    assert await link_count(db_session) == 0
    assert (await client.get(channels_url(monitor), headers=headers)).json()["total"] == 0


async def test_deleting_a_monitor_removes_its_links(client, headers, db_session):
    monitor = await make_monitor(client, headers)
    channel = await make_channel(client, headers, "a@example.com")
    await client.put(channels_url(monitor), json={"channel_ids": [channel]}, headers=headers)

    await client.delete(f"/api/v1/monitors/{monitor}", headers=headers)
    assert await link_count(db_session) == 0
    # The channel itself stays.
    assert (await client.get("/api/v1/alert-channels", headers=headers)).json()["total"] == 1
