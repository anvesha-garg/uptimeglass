"""Alert channel rules: limits, ownership, and which links a monitor has."""

import secrets
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import AlertChannel, Monitor, MonitorAlertChannel, User
from app.schemas.alert import ChannelCreate, ChannelOut
from app.services.monitors import check_url_is_safe

MAX_CHANNELS_PER_USER = 10


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
        # The same SSRF guard as monitor URLs. Part B checks again at send time.
        await check_url_is_safe(data.url)
        secret = secrets.token_urlsafe(32)
        config = {"url": data.url, "secret": secret}
        is_verified = True  # nothing to confirm for a webhook
    elif data.type == "email":
        config = {"address": data.address}  # confirmed in Part B
    else:
        config = {"link_code": secrets.token_urlsafe(16), "chat_id": None}  # linked in Part B

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
