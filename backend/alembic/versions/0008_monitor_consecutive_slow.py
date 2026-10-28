"""monitor consecutive_slow

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "monitors",
        sa.Column("consecutive_slow", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("monitors", "consecutive_slow")
