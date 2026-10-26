"""Talks to the Telegram Bot API. The bot token never appears in messages or logs."""

import httpx

from app.alerts.message import AlertSendError
from app.core.config import settings

API_URL = "https://api.telegram.org"
TIMEOUT_SECONDS = 15


async def _call(method: str, payload: dict, client: httpx.AsyncClient | None = None):
    token = settings.telegram_bot_token
    if not token:
        raise AlertSendError("Telegram is not configured on this server.")
    url = f"{API_URL}/bot{token}/{method}"  # the token is part of the URL, so we never print it
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, trust_env=False) as own_client:
                response = await own_client.post(url, json=payload)
        else:
            response = await client.post(url, json=payload)
    except httpx.HTTPError as error:
        raise AlertSendError(f"Telegram request failed ({type(error).__name__}).") from None
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code != 200 or not data.get("ok"):
        raise AlertSendError(f"Telegram answered with status {response.status_code}.")
    return data.get("result")


async def send_telegram(chat_id: int, text: str, client: httpx.AsyncClient | None = None) -> None:
    # No parse_mode: plain text cannot be broken by characters in a monitor name.
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    await _call("sendMessage", payload, client)


async def get_updates(offset: int | None, client: httpx.AsyncClient | None = None) -> list[dict]:
    payload: dict = {"timeout": 0, "allowed_updates": ["message"]}
    if offset is not None:
        payload["offset"] = offset
    return await _call("getUpdates", payload, client) or []
