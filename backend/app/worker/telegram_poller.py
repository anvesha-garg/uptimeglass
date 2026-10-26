"""Links Telegram chats to channels by polling the bot's messages (no public URL needed).

The user sends "/start <link_code>" to the bot. We read it with getUpdates, mark the
channel as verified and remember the chat id.
"""

import asyncio
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.alerts.message import AlertSendError
from app.alerts.telegram import get_updates, send_telegram
from app.core.config import settings
from app.models import AlertChannel

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 3.0


def extract_link(update: dict) -> tuple[int, str] | None:
    """Returns (chat_id, link_code) for a "/start <code>" message in a private chat."""
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    parts = (message.get("text") or "").split()
    if chat.get("type") != "private" or not isinstance(chat.get("id"), int):
        return None
    # "/start@MyBot code" is how Telegram sends it from some menus.
    if len(parts) != 2 or parts[0].split("@")[0] != "/start":
        return None
    return chat["id"], parts[1]


async def process_updates(db: AsyncSession, updates: list[dict]) -> list[int]:
    """Verify the matching channels. Returns the chat ids that were just linked."""
    linked: list[int] = []
    for update in updates:
        link = extract_link(update)
        if link is None:
            continue
        chat_id, code = link
        channel = await db.scalar(
            select(AlertChannel)
            .where(
                AlertChannel.type == "telegram",
                AlertChannel.is_verified.is_(False),
                AlertChannel.config["link_code"].astext == code,
            )
            .with_for_update()
        )
        if channel is None:
            continue
        channel.config = {"chat_id": chat_id}  # the one-time code is dropped
        channel.is_verified = True
        linked.append(chat_id)
    await db.commit()
    return linked


async def poll_once(
    session_factory: async_sessionmaker[AsyncSession],
    offset: int | None,
    client: httpx.AsyncClient | None = None,
) -> int | None:
    """One round of polling. Returns the offset to use next time."""
    updates = await get_updates(offset, client)
    if not updates:
        return offset
    async with session_factory() as db:
        linked = await process_updates(db, updates)
    for chat_id in linked:
        try:
            await send_telegram(chat_id, "Linked! You will get UptimeGlass alerts here.", client)
        except AlertSendError as error:
            logger.warning("Could not confirm the Telegram link: %s", error)
    return max(update.get("update_id", -1) for update in updates) + 1


async def run_telegram_polling(
    session_factory: async_sessionmaker[AsyncSession],
    stop_event: asyncio.Event,
    *,
    interval: float = POLL_INTERVAL_SECONDS,
) -> None:
    if not settings.telegram_bot_token:
        logger.info("TELEGRAM_BOT_TOKEN is empty, so Telegram linking is off.")
        return
    offset: int | None = None
    while not stop_event.is_set():
        try:
            offset = await poll_once(session_factory, offset)
        except AlertSendError as error:
            logger.warning("Telegram polling failed: %s", error)
        except Exception:
            logger.exception("Telegram polling crashed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            pass
