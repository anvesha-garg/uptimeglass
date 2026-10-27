import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CheckRollupHourly(Base):
    """One row per monitor per complete hour. Survives after raw results are pruned."""

    __tablename__ = "check_rollups_hourly"

    monitor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"), primary_key=True
    )
    hour: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    checks: Mapped[int] = mapped_column(Integer)
    failures: Mapped[int] = mapped_column(Integer)
    # Latency figures use successful checks only, so they are null if none succeeded.
    avg_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    p50_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    p99_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
