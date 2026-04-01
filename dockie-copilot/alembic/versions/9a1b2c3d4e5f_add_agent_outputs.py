"""add agent outputs

Revision ID: 9a1b2c3d4e5f
Revises: 5d6dfe7c9a21
Create Date: 2026-03-31 11:20:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "9a1b2c3d4e5f"
down_revision = "5d6dfe7c9a21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_outputs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=True),
        sa.Column("shipment_id", sa.String(length=64), nullable=True),
        sa.Column("output_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("preview_text", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["standby_agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_outputs_type_created", "agent_outputs", ["output_type", "created_at"], unique=False)
    op.create_index("ix_agent_outputs_user_created", "agent_outputs", ["user_id", "created_at"], unique=False)

    op.add_column("user_notifications", sa.Column("output_id", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_user_notifications_output_id_agent_outputs",
        "user_notifications",
        "agent_outputs",
        ["output_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_user_notifications_output_id_agent_outputs", "user_notifications", type_="foreignkey")
    op.drop_column("user_notifications", "output_id")
    op.drop_index("ix_agent_outputs_user_created", table_name="agent_outputs")
    op.drop_index("ix_agent_outputs_type_created", table_name="agent_outputs")
    op.drop_table("agent_outputs")
