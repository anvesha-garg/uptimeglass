import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.alerts.message import AlertSendError
from app.alerts.telegram import get_updates, send_telegram
from app.core.config import settings
from app.models import AlertChannel, User
from app.worker.telegram_poller import (
    extract_link,
    poll_once,
    process_updates,
    run_telegram_polling,
)

TOKEN = "123456:SECRET-TOKEN"


@pytest.fixture(autouse=True)
def bot_token(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TOKEN)


def client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def start_update(update_id: int, code: str, chat_id: int = 42, chat_type: str = "private") -> dict:
    return {
        "update_id": update_id,
        "message": {"text": f"/start {code}", "chat": {"id": chat_id, "type": chat_type}},
    }


async def make_channel(db, verified=False, config=None) -> AlertChannel:
    user = User(email=f"{uuid4()}@example.com", password_hash="x")
    db.add(user)
    await db.commit()
    channel = AlertChannel(
        user_id=user.id,
        type="telegram",
        config=config or {"link_code": "abc123", "chat_id": None},
        is_verified=verified,
    )
    db.add(channel)
    await db.commit()
    return channel


# ---------- sending ----------


async def test_send_telegram_posts_to_the_bot_api():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True, "result": {}})

    await send_telegram(42, "Hello", client=client_for(handler))
    (request,) = calls
    assert request.url.path == f"/bot{TOKEN}/sendMessage"
    assert json.loads(request.content) == {
        "chat_id": 42,
        "text": "Hello",
        "disable_web_page_preview": True,
    }


async def test_send_telegram_without_a_token_is_an_error(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    with pytest.raises(AlertSendError, match="not configured"):
        await send_telegram(42, "Hello")


async def test_telegram_api_errors_never_reveal_the_token():
    def handler(request):
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    with pytest.raises(AlertSendError) as error:
        await send_telegram(42, "Hello", client=client_for(handler))
    assert "401" in str(error.value)
    assert "SECRET-TOKEN" not in str(error.value)


async def test_network_errors_never_reveal_the_token():
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(AlertSendError) as error:
        await send_telegram(42, "Hello", client=client_for(handler))
    assert "ConnectError" in str(error.value)
    assert "SECRET-TOKEN" not in str(error.value)


async def test_get_updates_sends_the_offset_and_returns_the_list():
    payloads = []

    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": [{"update_id": 7}]})

    assert await get_updates(5, client_for(handler)) == [{"update_id": 7}]
    assert payloads[0]["offset"] == 5
    assert payloads[0]["timeout"] == 0


# ---------- understanding messages ----------


@pytest.mark.parametrize(
    ("update", "expected"),
    [
        (start_update(1, "abc"), (42, "abc")),
        (
            {"message": {"text": "/start@MyBot abc", "chat": {"id": 7, "type": "private"}}},
            (7, "abc"),
        ),
        ({"message": {"text": "/start", "chat": {"id": 7, "type": "private"}}}, None),
        ({"message": {"text": "hello abc", "chat": {"id": 7, "type": "private"}}}, None),
        (start_update(1, "abc", chat_type="group"), None),
        ({"edited_message": {"text": "/start abc"}}, None),
        ({"message": {"text": "/start abc", "chat": {"id": "7", "type": "private"}}}, None),
    ],
)
def test_extract_link(update, expected):
    assert extract_link(update) == expected


# ---------- linking channels ----------


async def test_a_matching_code_links_and_verifies_the_channel(db_session):
    channel = await make_channel(db_session)
    linked = await process_updates(db_session, [start_update(1, "abc123", chat_id=99)])

    assert linked == [99]
    await db_session.refresh(channel)
    assert channel.is_verified is True
    assert channel.config == {"chat_id": 99}  # the one-time code is gone


async def test_a_wrong_code_or_a_group_chat_changes_nothing(db_session):
    channel = await make_channel(db_session)
    updates = [start_update(1, "wrong"), start_update(2, "abc123", chat_type="group")]

    assert await process_updates(db_session, updates) == []
    await db_session.refresh(channel)
    assert channel.is_verified is False


async def test_an_already_linked_channel_is_not_taken_over(db_session):
    channel = await make_channel(db_session, verified=True, config={"chat_id": 5})
    assert await process_updates(db_session, [start_update(1, "abc123", chat_id=99)]) == []
    await db_session.refresh(channel)
    assert channel.config == {"chat_id": 5}


async def test_poll_once_links_confirms_and_advances_the_offset(db_session, engine):
    channel = await make_channel(db_session)
    calls = []

    def handler(request):
        method = request.url.path.rsplit("/", 1)[-1]
        calls.append((method, json.loads(request.content)))
        if method == "getUpdates":
            return httpx.Response(
                200, json={"ok": True, "result": [start_update(10, "abc123", 99)]}
            )
        return httpx.Response(200, json={"ok": True, "result": {}})

    factory = async_sessionmaker(engine, expire_on_commit=False)
    next_offset = await poll_once(factory, None, client_for(handler))

    assert next_offset == 11  # the last update id plus one
    await db_session.refresh(channel)
    assert channel.is_verified is True
    methods = [method for method, _ in calls]
    assert methods == ["getUpdates", "sendMessage"]
    assert calls[1][1]["chat_id"] == 99  # the user got a confirmation


async def test_polling_stays_off_without_a_token(monkeypatch, engine):
    import asyncio

    monkeypatch.setattr(settings, "telegram_bot_token", "")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    # Returns at once instead of looping forever.
    await asyncio.wait_for(run_telegram_polling(factory, asyncio.Event()), timeout=2)
