import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_monitor_id_status", "monitor_id", "status"),
        # The database itself refuses a second OPEN incident for the same monitor.
        Index(
            "uq_incidents_one_open_per_monitor",
            "monitor_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Deleting a monitor deletes its incidents.
    monitor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | resolved
    cause: Mapped[str] = mapped_column(String(20))  # the error type that started it
    details: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # filled in Phase 10
