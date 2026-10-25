"""Alert channels, and the choice of which channels each monitor uses."""

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.alert import (
    ChannelCreate,
    ChannelCreated,
    ChannelList,
    MonitorChannelsUpdate,
)
from app.services import alerts as service
from app.services.monitors import get_owned_monitor

router = APIRouter(tags=["alerts"])


@router.post("/alert-channels", response_model=ChannelCreated, status_code=201)
async def create_channel(body: ChannelCreate, user: CurrentUser, db: DbSession):
    channel, secret = await service.create_channel(db, user, body)
    out = service.channel_to_out(channel)
    return ChannelCreated(**out.model_dump(), secret=secret)


@router.get("/alert-channels", response_model=ChannelList)
async def list_channels(user: CurrentUser, db: DbSession):
    channels = await service.list_channels(db, user)
    return ChannelList(items=[service.channel_to_out(c) for c in channels], total=len(channels))


@router.delete("/alert-channels/{channel_id}", status_code=204)
async def delete_channel(channel_id: UUID, user: CurrentUser, db: DbSession) -> None:
    channel = await service.get_owned_channel(db, user, channel_id)
    await service.delete_channel(db, channel)


@router.get("/monitors/{monitor_id}/alert-channels", response_model=ChannelList)
async def get_monitor_channels(monitor_id: UUID, user: CurrentUser, db: DbSession):
    monitor = await get_owned_monitor(db, user, monitor_id)
    channels = await service.get_monitor_channels(db, monitor)
    return ChannelList(items=[service.channel_to_out(c) for c in channels], total=len(channels))


@router.put("/monitors/{monitor_id}/alert-channels", response_model=ChannelList)
async def set_monitor_channels(
    monitor_id: UUID, body: MonitorChannelsUpdate, user: CurrentUser, db: DbSession
):
    monitor = await get_owned_monitor(db, user, monitor_id)
    channels = await service.set_monitor_channels(db, user, monitor, body.channel_ids)
    return ChannelList(items=[service.channel_to_out(c) for c in channels], total=len(channels))
