from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    monitor_id: UUID
    started_at: datetime
    resolved_at: datetime | None
    status: str
    cause: str
    details: dict
    ai_summary: str | None


class IncidentList(BaseModel):
    items: list[IncidentOut]
    total: int
    limit: int
    offset: int
