"""incidents

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("monitor_id", sa.Uuid(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("cause", sa.String(length=20), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["monitor_id"],
            ["monitors.id"],
            name=op.f("fk_incidents_monitor_id_monitors"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
    )
    op.create_index(
        "ix_incidents_monitor_id_status", "incidents", ["monitor_id", "status"], unique=False
    )
    op.create_index(
        "uq_incidents_one_open_per_monitor",
        "incidents",
        ["monitor_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index("uq_incidents_one_open_per_monitor", table_name="incidents")
    op.drop_index("ix_incidents_monitor_id_status", table_name="incidents")
    op.drop_table("incidents")
