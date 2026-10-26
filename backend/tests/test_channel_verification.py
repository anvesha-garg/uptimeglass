from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.alerts.message import AlertSendError
from app.models import AlertChannel
from app.services import alerts as alerts_service
from app.services.alerts import MAX_CODE_ATTEMPTS

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


@pytest.fixture
def mailbox(monkeypatch) -> list[dict]:
    """Replaces the email sender, so nothing is sent."""
    sent: list[dict] = []

    async def fake_send_email(to, subject, body):
        sent.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(alerts_service, "send_email", fake_send_email)
    return sent


async def make_email_channel(client, headers, address="me@example.com") -> str:
    response = await client.post(
        "/api/v1/alert-channels", json={"type": "email", "address": address}, headers=headers
    )
    return response.json()["id"]


async def stored_channel(db) -> AlertChannel:
    # populate_existing: read the current row, not an object the session saw earlier.
    return await db.scalar(select(AlertChannel).execution_options(populate_existing=True))


async def change_config(db, **changes) -> None:
    channel = await stored_channel(db)
    channel.config = {**channel.config, **changes}
    await db.commit()


def url(channel_id: str, action: str) -> str:
    return f"/api/v1/alert-channels/{channel_id}/{action}"


# ---------- send-code ----------


async def test_send_code_emails_a_six_digit_code(client, headers, mailbox, db_session):
    channel = await make_email_channel(client, headers)
    response = await client.post(url(channel, "send-code"), headers=headers)

    assert response.status_code == 204
    (mail,) = mailbox
    assert mail["to"] == "me@example.com"
    code = (await stored_channel(db_session)).config["verify_code"]
    assert len(code) == 6 and code.isdigit()
    assert code in mail["body"]


async def test_a_second_code_within_a_minute_is_refused(client, headers, mailbox):
    channel = await make_email_channel(client, headers)
    await client.post(url(channel, "send-code"), headers=headers)

    response = await client.post(url(channel, "send-code"), headers=headers)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert len(mailbox) == 1


async def test_a_failed_send_stores_no_code(client, headers, monkeypatch, db_session):
    async def broken_send_email(to, subject, body):
        raise AlertSendError("Email is not configured on this server.")

    monkeypatch.setattr(alerts_service, "send_email", broken_send_email)
    channel = await make_email_channel(client, headers)

    response = await client.post(url(channel, "send-code"), headers=headers)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "send_failed"
    assert "verify_code" not in (await stored_channel(db_session)).config


async def test_only_email_channels_have_codes(client, headers, mailbox):
    created = await client.post(
        "/api/v1/alert-channels", json={"type": "telegram"}, headers=headers
    )
    response = await client.post(url(created.json()["id"], "send-code"), headers=headers)
    assert response.status_code == 422


# ---------- verify ----------


async def test_the_right_code_verifies_the_channel(client, headers, mailbox, db_session):
    channel = await make_email_channel(client, headers)
    await client.post(url(channel, "send-code"), headers=headers)
    code = (await stored_channel(db_session)).config["verify_code"]

    response = await client.post(url(channel, "verify"), json={"code": code}, headers=headers)
    assert response.status_code == 200
    assert response.json()["is_verified"] is True
    # The code is removed from storage once it has been used.
    assert (await stored_channel(db_session)).config == {"address": "me@example.com"}


async def test_a_wrong_code_is_refused(client, headers, mailbox, db_session):
    channel = await make_email_channel(client, headers)
    await client.post(url(channel, "send-code"), headers=headers)
    real = (await stored_channel(db_session)).config["verify_code"]
    wrong = "000000" if real != "000000" else "111111"

    response = await client.post(url(channel, "verify"), json={"code": wrong}, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_code"
    assert (await stored_channel(db_session)).is_verified is False


async def test_too_many_wrong_codes_lock_the_code(client, headers, mailbox, db_session):
    channel = await make_email_channel(client, headers)
    await client.post(url(channel, "send-code"), headers=headers)
    real = (await stored_channel(db_session)).config["verify_code"]
    wrong = "000000" if real != "000000" else "111111"

    for _ in range(MAX_CODE_ATTEMPTS):
        await client.post(url(channel, "verify"), json={"code": wrong}, headers=headers)

    # Even the right code is refused now: a new one must be requested.
    response = await client.post(url(channel, "verify"), json={"code": real}, headers=headers)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "too_many_attempts"


async def test_an_expired_code_is_refused(client, headers, mailbox, db_session):
    channel = await make_email_channel(client, headers)
    await client.post(url(channel, "send-code"), headers=headers)
    old = (datetime.now(UTC) - timedelta(minutes=20)).isoformat()
    await change_config(db_session, code_sent_at=old)
    code = (await stored_channel(db_session)).config["verify_code"]

    response = await client.post(url(channel, "verify"), json={"code": code}, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "code_expired"


async def test_verifying_before_asking_for_a_code_is_refused(client, headers):
    channel = await make_email_channel(client, headers)
    response = await client.post(url(channel, "verify"), json={"code": "123456"}, headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "code_not_sent"


async def test_a_malformed_code_is_a_validation_error(client, headers):
    channel = await make_email_channel(client, headers)
    for bad in ("12345", "1234567", "abcdef", ""):
        response = await client.post(url(channel, "verify"), json={"code": bad}, headers=headers)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


async def test_a_verified_channel_cannot_be_verified_again(client, headers, mailbox, db_session):
    channel = await make_email_channel(client, headers)
    await client.post(url(channel, "send-code"), headers=headers)
    code = (await stored_channel(db_session)).config["verify_code"]
    await client.post(url(channel, "verify"), json={"code": code}, headers=headers)

    response = await client.post(url(channel, "send-code"), headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_verified"


async def test_other_users_cannot_verify_or_test_a_channel(client, headers, other_headers, mailbox):
    channel = await make_email_channel(client, headers)
    assert (await client.post(url(channel, "send-code"), headers=other_headers)).status_code == 404
    verify = await client.post(
        url(channel, "verify"), json={"code": "123456"}, headers=other_headers
    )
    assert verify.status_code == 404
    assert (await client.post(url(channel, "test"), headers=other_headers)).status_code == 404


# ---------- test message ----------


async def test_a_test_message_goes_through_a_verified_channel(client, headers, monkeypatch):
    sent = []

    async def fake_send_to_channel(channel, message):
        sent.append((channel.type, message.kind))

    monkeypatch.setattr(alerts_service, "send_to_channel", fake_send_to_channel)
    created = await client.post(
        "/api/v1/alert-channels",
        json={"type": "webhook", "url": "https://example.com/hook"},
        headers=headers,
    )

    response = await client.post(url(created.json()["id"], "test"), headers=headers)
    assert response.status_code == 204
    assert sent == [("webhook", "test")]


async def test_an_unverified_channel_cannot_send_a_test(client, headers):
    channel = await make_email_channel(client, headers)
    response = await client.post(url(channel, "test"), headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "channel_not_verified"


async def test_a_failing_test_message_is_a_502(client, headers, monkeypatch):
    async def broken_send_to_channel(channel, message):
        raise AlertSendError("The webhook answered with status 500.")

    monkeypatch.setattr(alerts_service, "send_to_channel", broken_send_to_channel)
    created = await client.post(
        "/api/v1/alert-channels",
        json={"type": "webhook", "url": "https://example.com/hook"},
        headers=headers,
    )

    response = await client.post(url(created.json()["id"], "test"), headers=headers)
    assert response.status_code == 502
    assert response.json()["error"] == {
        "code": "send_failed",
        "message": "The webhook answered with status 500.",
    }
