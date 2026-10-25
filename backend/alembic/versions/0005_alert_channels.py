"""alert_channels and monitor_alert_channels

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_channels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_alert_channels_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_channels")),
    )
    op.create_index(op.f("ix_alert_channels_user_id"), "alert_channels", ["user_id"], unique=False)

    op.create_table(
        "monitor_alert_channels",
        sa.Column("monitor_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["monitor_id"],
            ["monitors.id"],
            name=op.f("fk_monitor_alert_channels_monitor_id_monitors"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["alert_channels.id"],
            name=op.f("fk_monitor_alert_channels_channel_id_alert_channels"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("monitor_id", "channel_id", name=op.f("pk_monitor_alert_channels")),
    )
    op.create_index(
        op.f("ix_monitor_alert_channels_channel_id"),
        "monitor_alert_channels",
        ["channel_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_monitor_alert_channels_channel_id"), table_name="monitor_alert_channels")
    op.drop_table("monitor_alert_channels")
    op.drop_index(op.f("ix_alert_channels_user_id"), table_name="alert_channels")
    op.drop_table("alert_channels")
