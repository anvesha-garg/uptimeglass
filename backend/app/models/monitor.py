import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Allowed values for "status". Stored as text so adding a state later needs no type migration.
MONITOR_STATUSES = ("PENDING", "UP", "DEGRADED", "DOWN", "PAUSED")


class Monitor(Base):
    __tablename__ = "monitors"
    __table_args__ = (
        # The scheduler asks "which unpaused monitors are due?". A partial index keeps that fast.
        Index(
            "ix_monitors_next_check_at_active",
            "next_check_at",
            postgresql_where=text("NOT is_paused"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(2048))
    method: Mapped[str] = mapped_column(String(10), default="GET")
    interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10)
    expected_status: Mapped[int] = mapped_column(Integer, default=200)
    keyword: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_paused: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(String(10), default="PENDING")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    consecutive_successes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_check_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ssl_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
