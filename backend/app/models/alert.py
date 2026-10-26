import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlertChannel(Base):
    __tablename__ = "alert_channels"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(10))  # email | telegram | webhook
    # email: {"address"}   webhook: {"url", "secret"}   telegram: {"link_code", "chat_id"}
    config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    # The dispatcher only sends to verified channels.
    is_verified: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MonitorAlertChannel(Base):
    """Which channels a monitor alerts. Deleting either side deletes the link."""

    __tablename__ = "monitor_alert_channels"

    monitor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"), primary_key=True
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alert_channels.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class AlertEvent(Base):
    """One row per alert attempt. The unique index is what stops duplicate alerts."""

    __tablename__ = "alert_events"
    __table_args__ = (
        Index("uq_alert_events_channel_dedupe", "channel_id", "dedupe_key", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Empty for SSL expiry warnings, which belong to a monitor and not to an incident.
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"), index=True
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alert_channels.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(12))  # opened | resolved | ssl_expiry
    # opened:<incident>, resolved:<incident>, or ssl:<monitor>:<days>:<expiry date>
    dedupe_key: Mapped[str] = mapped_column(String(120))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    success: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
