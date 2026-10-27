"""check_rollups_hourly

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "check_rollups_hourly",
        sa.Column("monitor_id", sa.Uuid(), nullable=False),
        sa.Column("hour", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checks", sa.Integer(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("avg_ms", sa.Float(), nullable=True),
        sa.Column("p50_ms", sa.Float(), nullable=True),
        sa.Column("p95_ms", sa.Float(), nullable=True),
        sa.Column("p99_ms", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["monitor_id"],
            ["monitors.id"],
            name=op.f("fk_check_rollups_hourly_monitor_id_monitors"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("monitor_id", "hour", name=op.f("pk_check_rollups_hourly")),
    )


def downgrade() -> None:
    op.drop_table("check_rollups_hourly")
