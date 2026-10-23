import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, desc, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CheckResult(Base):
    __tablename__ = "check_results"
    __table_args__ = (
        # "Latest results of one monitor" is the most common query (charts, recent checks).
        Index("ix_check_results_monitor_id_checked_at", "monitor_id", desc("checked_at")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Deleting a monitor deletes its history.
    monitor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    success: Mapped[bool]
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # timeout | dns | connection | ssl | status_code | keyword | blocked
    error_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
