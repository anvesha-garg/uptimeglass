"""Alert channel rules: limits, ownership, verification and test messages."""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.mailer import send_email
from app.alerts.message import AlertSendError, make_test_message
from app.alerts.sender import send_to_channel
from app.core.errors import AppError
from app.models import AlertChannel, Monitor, MonitorAlertChannel, User
from app.schemas.alert import ChannelCreate, ChannelOut
from app.services.monitors import check_url_is_safe

MAX_CHANNELS_PER_USER = 10
CODE_RESEND_SECONDS = 60  # at most one verification email per minute
CODE_VALID_MINUTES = 15
MAX_CODE_ATTEMPTS = 5


def channel_to_out(channel: AlertChannel) -> ChannelOut:
    config = channel.config
    link_code = None
    if channel.type == "email":
        target = config["address"]
    elif channel.type == "webhook":
        target = config["url"]
    else:
        linked = config.get("chat_id") is not None
        target = "Telegram chat linked" if linked else "Waiting for you to link the Telegram bot"
        if not channel.is_verified:
            link_code = config.get("link_code")
    return ChannelOut(
        id=channel.id,
        type=channel.type,
        target=target,
        is_verified=channel.is_verified,
        link_code=link_code,
        created_at=channel.created_at,
    )


async def get_owned_channel(db: AsyncSession, user: User, channel_id: UUID) -> AlertChannel:
    """Someone else's channel looks missing."""
    channel = await db.scalar(
        select(AlertChannel).where(AlertChannel.id == channel_id, AlertChannel.user_id == user.id)
    )
    if channel is None:
        raise AppError(404, "not_found", "Alert channel not found.")
    return channel


async def list_channels(db: AsyncSession, user: User) -> list[AlertChannel]:
    rows = await db.scalars(
        select(AlertChannel)
        .where(AlertChannel.user_id == user.id)
        .order_by(AlertChannel.created_at, AlertChannel.id)
    )
    return list(rows)


async def create_channel(
    db: AsyncSession, user: User, data: ChannelCreate
) -> tuple[AlertChannel, str | None]:
    """Returns the channel and the webhook secret (None for other types)."""
    secret = None
    is_verified = False
    if data.type == "webhook":
        # The same SSRF guard as monitor URLs. The sender checks again at send time.
        await check_url_is_safe(data.url)
        secret = secrets.token_urlsafe(32)
        config = {"url": data.url, "secret": secret}
        is_verified = True  # nothing to confirm for a webhook
    elif data.type == "email":
        config = {"address": data.address}  # confirmed with a code, see send_email_code
    else:
        config = {"link_code": secrets.token_urlsafe(16), "chat_id": None}  # linked by the bot

    # Lock the user row, so two simultaneous creates cannot both pass the limit check.
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    count = await db.scalar(
        select(func.count()).select_from(AlertChannel).where(AlertChannel.user_id == user.id)
    )
    if count >= MAX_CHANNELS_PER_USER:
        raise AppError(
            409,
            "channel_limit_reached",
            f"You can have at most {MAX_CHANNELS_PER_USER} alert channels.",
        )

    channel = AlertChannel(user_id=user.id, type=data.type, config=config, is_verified=is_verified)
    db.add(channel)
    await db.commit()
    await db.refresh(channel)  # loads created_at, which the database filled in
    return channel, secret


async def delete_channel(db: AsyncSession, channel: AlertChannel) -> None:
    # Links to monitors disappear too (ON DELETE CASCADE).
    await db.delete(channel)
    await db.commit()


# ---------- email verification ----------


def _require_unverified_email(channel: AlertChannel) -> None:
    if channel.type != "email":
        raise AppError(422, "validation_error", "Only email channels need a verification code.")
    if channel.is_verified:
        raise AppError(409, "already_verified", "This channel is already verified.")


async def send_email_code(db: AsyncSession, channel: AlertChannel) -> None:
    _require_unverified_email(channel)
    config = channel.config
    now = datetime.now(UTC)
    sent_at = config.get("code_sent_at")
    if sent_at and now - datetime.fromisoformat(sent_at) < timedelta(seconds=CODE_RESEND_SECONDS):
        raise AppError(429, "rate_limited", "Wait a minute before asking for another code.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    body = (
        f"Your UptimeGlass verification code is {code}.\n"
        f"It works for {CODE_VALID_MINUTES} minutes."
    )
    try:
        await send_email(config["address"], "Your UptimeGlass verification code", body)
    except AlertSendError as error:
        raise AppError(502, "send_failed", str(error)) from None

    # Saved only after the email went out, so a failed send does not start the one-minute wait.
    channel.config = {
        **config,
        "verify_code": code,
        "verify_attempts": 0,
        "code_sent_at": now.isoformat(),
    }
    await db.commit()


async def verify_email(db: AsyncSession, channel: AlertChannel, code: str) -> AlertChannel:
    _require_unverified_email(channel)
    config = channel.config
    stored = config.get("verify_code")
    if not stored:
        raise AppError(409, "code_not_sent", "Ask for a verification code first.")
    attempts = config.get("verify_attempts", 0)
    if attempts >= MAX_CODE_ATTEMPTS:
        raise AppError(429, "too_many_attempts", "Too many wrong codes. Ask for a new one.")
    sent_at = datetime.fromisoformat(config["code_sent_at"])
    if datetime.now(UTC) - sent_at > timedelta(minutes=CODE_VALID_MINUTES):
        raise AppError(422, "code_expired", "That code has expired. Ask for a new one.")

    if not secrets.compare_digest(code, stored):  # constant-time comparison
        channel.config = {**config, "verify_attempts": attempts + 1}
        await db.commit()
        raise AppError(422, "invalid_code", "That code is not correct.")

    channel.is_verified = True
    channel.config = {"address": config["address"]}  # the code is no longer needed
    await db.commit()
    return channel


# ---------- test message ----------


async def send_test(channel: AlertChannel) -> None:
    if not channel.is_verified:
        raise AppError(409, "channel_not_verified", "Verify the channel before sending a test.")
    try:
        await send_to_channel(channel, make_test_message())
    except AlertSendError as error:
        raise AppError(502, "send_failed", str(error)) from None


# ---------- monitor links ----------


async def get_monitor_channels(db: AsyncSession, monitor: Monitor) -> list[AlertChannel]:
    rows = await db.scalars(
        select(AlertChannel)
        .join(MonitorAlertChannel, MonitorAlertChannel.channel_id == AlertChannel.id)
        .where(MonitorAlertChannel.monitor_id == monitor.id)
        .order_by(AlertChannel.created_at, AlertChannel.id)
    )
    return list(rows)


async def set_monitor_channels(
    db: AsyncSession, user: User, monitor: Monitor, channel_ids: list[UUID]
) -> list[AlertChannel]:
    """Replace the monitor's channels. All or nothing: one foreign ID changes nothing."""
    unique_ids = list(dict.fromkeys(channel_ids))
    channels: list[AlertChannel] = []
    if unique_ids:
        rows = await db.scalars(
            select(AlertChannel).where(
                AlertChannel.user_id == user.id, AlertChannel.id.in_(unique_ids)
            )
        )
        channels = list(rows)
        if len(channels) != len(unique_ids):
            # Same answer for "does not exist" and "belongs to someone else".
            raise AppError(404, "not_found", "Alert channel not found.")

    await db.execute(
        delete(MonitorAlertChannel).where(MonitorAlertChannel.monitor_id == monitor.id)
    )
    db.add_all(MonitorAlertChannel(monitor_id=monitor.id, channel_id=c.id) for c in channels)
    await db.commit()
    return sorted(channels, key=lambda c: (c.created_at, c.id))
