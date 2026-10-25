import pytest
from sqlalchemy import select

from app.models import AlertChannel
from app.services.alerts import MAX_CHANNELS_PER_USER

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


async def create_channel(client, headers, **body):
    return await client.post("/api/v1/alert-channels", json=body, headers=headers)


async def test_channels_require_login(client):
    assert (await client.get("/api/v1/alert-channels")).status_code == 401
    response = await client.post("/api/v1/alert-channels", json={"type": "email"})
    assert response.status_code == 401


# ---------- create ----------


async def test_create_webhook_returns_the_secret_once(client, headers, db_session):
    response = await create_channel(client, headers, type="webhook", url="https://example.com/hook")
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "webhook"
    assert data["target"] == "https://example.com/hook"
    assert data["is_verified"] is True
    assert len(data["secret"]) >= 32

    # The secret is stored, because Part B needs it to sign webhooks.
    stored = await db_session.scalar(select(AlertChannel))
    assert stored.config["secret"] == data["secret"]


async def test_secret_is_never_shown_again(client, headers):
    created = (
        await create_channel(client, headers, type="webhook", url="https://example.com/hook")
    ).json()
    listing = await client.get("/api/v1/alert-channels", headers=headers)
    assert created["secret"] not in listing.text
    assert "secret" not in listing.json()["items"][0]


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/hook",
        "http://127.0.0.1/hook",
        "http://internal.example.com/hook",
    ],
)
async def test_unsafe_webhook_urls_are_rejected(client, headers, url):
    response = await create_channel(client, headers, type="webhook", url=url)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_url"


async def test_create_email_channel_is_unverified(client, headers):
    response = await create_channel(client, headers, type="email", address="Me@Example.com")
    assert response.status_code == 201
    data = response.json()
    assert data["target"] == "me@example.com"
    assert data["is_verified"] is False
    assert data["secret"] is None
    assert data["link_code"] is None


async def test_create_telegram_channel_waits_for_linking(client, headers):
    response = await create_channel(client, headers, type="telegram")
    assert response.status_code == 201
    data = response.json()
    assert data["is_verified"] is False
    assert data["link_code"]
    assert data["target"].startswith("Waiting")


@pytest.mark.parametrize(
    "body",
    [
        {"type": "email"},
        {"type": "email", "address": "not-an-email"},
        {"type": "webhook"},
        {"type": "sms"},
        {},
    ],
)
async def test_invalid_channels_are_rejected(client, headers, body):
    response = await create_channel(client, headers, **body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_channel_limit_is_enforced(client, headers):
    for number in range(MAX_CHANNELS_PER_USER):
        response = await create_channel(
            client, headers, type="email", address=f"user{number}@example.com"
        )
        assert response.status_code == 201
    response = await create_channel(
        client, headers, type="email", address="one-too-many@example.com"
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "channel_limit_reached"


# ---------- list and delete ----------


async def test_list_returns_only_own_channels(client, headers, other_headers):
    await create_channel(client, headers, type="email", address="mine@example.com")
    await create_channel(client, other_headers, type="email", address="theirs@example.com")

    data = (await client.get("/api/v1/alert-channels", headers=headers)).json()
    assert data["total"] == 1
    assert data["items"][0]["target"] == "mine@example.com"


async def test_delete_removes_the_channel(client, headers):
    created = (await create_channel(client, headers, type="email", address="a@example.com")).json()
    response = await client.delete(f"/api/v1/alert-channels/{created['id']}", headers=headers)
    assert response.status_code == 204
    assert (await client.get("/api/v1/alert-channels", headers=headers)).json()["total"] == 0


async def test_other_users_cannot_delete_a_channel(client, headers, other_headers):
    created = (await create_channel(client, headers, type="email", address="a@example.com")).json()
    url = f"/api/v1/alert-channels/{created['id']}"

    assert (await client.delete(url, headers=other_headers)).status_code == 404
    # Still there for the owner.
    assert (await client.get("/api/v1/alert-channels", headers=headers)).json()["total"] == 1
