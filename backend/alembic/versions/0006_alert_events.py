"""alert_events

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=True),
        sa.Column("monitor_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("dedupe_key", sa.String(length=120), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("success", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_alert_events_incident_id_incidents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["monitor_id"],
            ["monitors.id"],
            name=op.f("fk_alert_events_monitor_id_monitors"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["alert_channels.id"],
            name=op.f("fk_alert_events_channel_id_alert_channels"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_events")),
    )
    op.create_index(op.f("ix_alert_events_incident_id"), "alert_events", ["incident_id"])
    op.create_index(op.f("ix_alert_events_monitor_id"), "alert_events", ["monitor_id"])
    op.create_index(
        "uq_alert_events_channel_dedupe",
        "alert_events",
        ["channel_id", "dedupe_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_alert_events_channel_dedupe", table_name="alert_events")
    op.drop_index(op.f("ix_alert_events_monitor_id"), table_name="alert_events")
    op.drop_index(op.f("ix_alert_events_incident_id"), table_name="alert_events")
    op.drop_table("alert_events")
