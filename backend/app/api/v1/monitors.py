"""Monitor CRUD. Every route needs login and only sees the caller's own monitors."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models import Monitor
from app.schemas.monitor import MonitorCreate, MonitorList, MonitorOut, MonitorUpdate
from app.services import monitors as service

router = APIRouter(prefix="/monitors", tags=["monitors"])

# Columns that cannot be null: sending null for them is a mistake, not "remove".
NOT_NULLABLE_FIELDS = (
    "name",
    "url",
    "method",
    "interval_seconds",
    "timeout_seconds",
    "expected_status",
)


@router.post("", response_model=MonitorOut, status_code=201)
async def create_monitor(body: MonitorCreate, user: CurrentUser, db: DbSession):
    return await service.create_monitor(db, user, body.model_dump())


@router.get("", response_model=MonitorList)
async def list_monitors(
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    total = await db.scalar(
        select(func.count()).select_from(Monitor).where(Monitor.user_id == user.id)
    )
    rows = await db.scalars(
        select(Monitor)
        .where(Monitor.user_id == user.id)
        .order_by(Monitor.created_at.desc(), Monitor.id)
        .limit(limit)
        .offset(offset)
    )
    return MonitorList(items=list(rows), total=total, limit=limit, offset=offset)


@router.get("/{monitor_id}", response_model=MonitorOut)
async def get_monitor(monitor_id: UUID, user: CurrentUser, db: DbSession):
    return await service.get_owned_monitor(db, user, monitor_id)


@router.patch("/{monitor_id}", response_model=MonitorOut)
async def update_monitor(monitor_id: UUID, body: MonitorUpdate, user: CurrentUser, db: DbSession):
    monitor = await service.get_owned_monitor(db, user, monitor_id)
    # exclude_unset: only the fields the client actually sent.
    changes = body.model_dump(exclude_unset=True)
    for field in NOT_NULLABLE_FIELDS:
        if field in changes and changes[field] is None:
            del changes[field]
    return await service.update_monitor(db, monitor, changes)


@router.delete("/{monitor_id}", status_code=204)
async def delete_monitor(monitor_id: UUID, user: CurrentUser, db: DbSession) -> None:
    monitor = await service.get_owned_monitor(db, user, monitor_id)
    await db.delete(monitor)
    await db.commit()


@router.post("/{monitor_id}/pause", response_model=MonitorOut)
async def pause_monitor(monitor_id: UUID, user: CurrentUser, db: DbSession):
    monitor = await service.get_owned_monitor(db, user, monitor_id)
    return await service.pause_monitor(db, monitor)


@router.post("/{monitor_id}/resume", response_model=MonitorOut)
async def resume_monitor(monitor_id: UUID, user: CurrentUser, db: DbSession):
    monitor = await service.get_owned_monitor(db, user, monitor_id)
    return await service.resume_monitor(db, monitor)
