"""add position lookup indexes

Revision ID: d4f6e8a1b2c3
Revises: c1f4e2a9b7d3
Create Date: 2026-03-31 19:10:00.000000
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "d4f6e8a1b2c3"
down_revision = "c1f4e2a9b7d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_positions_mmsi_observed_at", "positions", ["mmsi", "observed_at"], unique=False)
    op.create_index("ix_positions_imo_observed_at", "positions", ["imo", "observed_at"], unique=False)
    op.create_index(
        "ix_latest_positions_imo_observed_at",
        "latest_positions",
        ["imo", "observed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_latest_positions_imo_observed_at", table_name="latest_positions")
    op.drop_index("ix_positions_imo_observed_at", table_name="positions")
    op.drop_index("ix_positions_mmsi_observed_at", table_name="positions")
