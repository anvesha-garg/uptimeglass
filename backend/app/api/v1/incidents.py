"""Read-only list of the caller's incidents."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models import Incident, Monitor
from app.schemas.incident import IncidentList

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=IncidentList)
async def list_incidents(
    user: CurrentUser,
    db: DbSession,
    status: Literal["open", "resolved"] | None = None,
    monitor_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    # Joining on the monitor's owner means nobody sees another user's incidents.
    conditions = [Monitor.user_id == user.id]
    if status is not None:
        conditions.append(Incident.status == status)
    if monitor_id is not None:
        conditions.append(Incident.monitor_id == monitor_id)

    total = await db.scalar(
        select(func.count())
        .select_from(Incident)
        .join(Monitor, Monitor.id == Incident.monitor_id)
        .where(*conditions)
    )
    rows = await db.scalars(
        select(Incident)
        .join(Monitor, Monitor.id == Incident.monitor_id)
        .where(*conditions)
        .order_by(Incident.started_at.desc(), Incident.id)
        .limit(limit)
        .offset(offset)
    )
    return IncidentList(items=list(rows), total=total, limit=limit, offset=offset)
