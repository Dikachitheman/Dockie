"""expand standby run action_executed

Revision ID: c1f4e2a9b7d3
Revises: 9a1b2c3d4e5f
Create Date: 2026-03-31 17:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1f4e2a9b7d3"
down_revision = "9a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "standby_agent_runs",
        "action_executed",
        existing_type=sa.String(length=32),
        type_=sa.String(length=128),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "standby_agent_runs",
        "action_executed",
        existing_type=sa.String(length=128),
        type_=sa.String(length=32),
        existing_nullable=True,
    )
