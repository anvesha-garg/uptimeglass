import pytest

from app.alerts import sender
from app.alerts.message import AlertSendError, make_test_message
from app.models import AlertChannel


@pytest.fixture
def calls(monkeypatch) -> list[tuple]:
    recorded: list[tuple] = []

    async def fake_webhook(config, message):
        recorded.append(("webhook", config["url"]))

    async def fake_email(to, subject, body):
        recorded.append(("email", to, subject))

    async def fake_telegram(chat_id, text):
        recorded.append(("telegram", chat_id))

    monkeypatch.setattr(sender, "send_webhook", fake_webhook)
    monkeypatch.setattr(sender, "send_email", fake_email)
    monkeypatch.setattr(sender, "send_telegram", fake_telegram)
    return recorded


def channel(type_: str, config: dict, verified: bool = True) -> AlertChannel:
    return AlertChannel(type=type_, config=config, is_verified=verified)


async def test_each_type_goes_to_its_own_sender(calls):
    message = make_test_message()
    await sender.send_to_channel(channel("webhook", {"url": "https://x.test/h"}), message)
    await sender.send_to_channel(channel("email", {"address": "a@example.com"}), message)
    await sender.send_to_channel(channel("telegram", {"chat_id": 42}), message)

    assert calls == [
        ("webhook", "https://x.test/h"),
        ("email", "a@example.com", "UptimeGlass test alert"),
        ("telegram", 42),
    ]


async def test_an_unverified_channel_is_never_used(calls):
    with pytest.raises(AlertSendError, match="not verified"):
        await sender.send_to_channel(
            channel("email", {"address": "a@example.com"}, verified=False), make_test_message()
        )
    assert calls == []


async def test_an_unknown_type_is_an_error(calls):
    with pytest.raises(AlertSendError):
        await sender.send_to_channel(channel("sms", {}), make_test_message())
