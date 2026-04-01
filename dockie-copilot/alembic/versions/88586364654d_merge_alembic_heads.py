"""merge alembic heads

Revision ID: 88586364654d
Revises: a7b3c9d2e4f6, d4f6e8a1b2c3
Create Date: 2026-04-01 08:44:02.571488
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '88586364654d'
down_revision = ('a7b3c9d2e4f6', 'd4f6e8a1b2c3')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
