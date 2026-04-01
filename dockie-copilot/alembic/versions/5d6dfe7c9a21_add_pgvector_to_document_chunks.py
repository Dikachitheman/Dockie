"""add pgvector to document chunks

Revision ID: 5d6dfe7c9a21
Revises: eca054a3dbbd
Create Date: 2026-03-30 22:40:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision = "5d6dfe7c9a21"
down_revision = "eca054a3dbbd"
branch_labels = None
depends_on = None


def _vector_backend() -> str:
    context = op.get_context()
    return context.config.attributes.get("knowledge_vector_backend", "array").lower()


def upgrade() -> None:
    backend = _vector_backend()
    if backend == "pgvector":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        embedding_type = Vector(1536)
    else:
        embedding_type = sa.ARRAY(sa.Float())

    op.add_column("document_chunks", sa.Column("embedding", embedding_type, nullable=True))
    op.add_column("document_chunks", sa.Column("embedding_model", sa.String(length=64), nullable=True))
    op.add_column("document_chunks", sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_document_chunks_embedding_model_embedded_at",
        "document_chunks",
        ["embedding_model", "embedded_at"],
        unique=False,
    )
    if backend == "pgvector":
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_ivfflat
            ON document_chunks
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
            """
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_ivfflat")
    op.drop_index("ix_document_chunks_embedding_model_embedded_at", table_name="document_chunks")
    op.drop_column("document_chunks", "embedded_at")
    op.drop_column("document_chunks", "embedding_model")
    op.drop_column("document_chunks", "embedding")
