"""
Embedding helpers for vector-backed knowledge retrieval.

This module isolates OpenAI embedding calls so application services can use a
small interface with safe availability checks and fallback behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.orm import DocumentChunk

settings = get_settings()
logger = get_logger(__name__)


class EmbeddingService:
    def __init__(self) -> None:
        self._client = None

    def is_available(self) -> bool:
        return bool(settings.knowledge_vector_enabled and settings.openai_api_key)

    def unavailable_reason(self) -> str | None:
        if not settings.knowledge_vector_enabled:
            return "knowledge vectors are disabled"
        if not settings.openai_api_key:
            return "OPENAI_API_KEY is not configured"
        return None

    def supports_vector_search(self) -> bool:
        return settings.knowledge_vector_backend.lower() == "pgvector"

    async def embed_text(self, text: str) -> list[float] | None:
        results = await self.embed_texts([text])
        return results[0] if results else None

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not self.is_available():
            logger.warning("knowledge_embeddings_unavailable", reason=self.unavailable_reason())
            return []

        clean_inputs = [text.strip() for text in texts if text and text.strip()]
        if not clean_inputs:
            return []

        try:
            client = self._get_client()
            response = await client.embeddings.create(
                model=settings.knowledge_embedding_model,
                input=clean_inputs,
                dimensions=settings.knowledge_embedding_dimensions,
            )
        except Exception as exc:
            if "insufficient_quota" in str(exc):
                logger.warning("knowledge_embedding_quota_exceeded", model=settings.knowledge_embedding_model)
            logger.warning("knowledge_embedding_request_failed", error=str(exc), count=len(clean_inputs))
            return []

        vectors = [list(item.embedding) for item in response.data]
        logger.info(
            "knowledge_embeddings_created",
            model=settings.knowledge_embedding_model,
            count=len(vectors),
        )
        return vectors

    def _get_client(self):
        if self._client is not None:
            return self._client

        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client


def _chunk_embedding_text(chunk: DocumentChunk) -> str:
    return " ".join(part for part in [chunk.title or "", chunk.content] if part).strip()


async def apply_embeddings_to_chunks(chunks: Sequence[DocumentChunk]) -> int:
    if not embedding_service.is_available():
        return 0

    chunk_list = list(chunks)
    if not chunk_list:
        return 0

    inputs = [_chunk_embedding_text(chunk) for chunk in chunk_list]
    vectors = await embedding_service.embed_texts(inputs)
    if len(vectors) != len(chunk_list):
        logger.warning(
            "knowledge_embedding_count_mismatch",
            expected=len(chunk_list),
            returned=len(vectors),
        )
        return 0

    embedded_at = datetime.now(timezone.utc)
    for chunk, vector in zip(chunk_list, vectors, strict=True):
        chunk.embedding = vector
        chunk.embedding_model = settings.knowledge_embedding_model
        chunk.embedded_at = embedded_at
        metadata = dict(getattr(chunk, "chunk_metadata", None) or {})
        metadata["embedding_version"] = settings.knowledge_embedding_version
        chunk.chunk_metadata = metadata
    return len(chunk_list)


async def backfill_document_chunk_embeddings(
    session: AsyncSession,
    *,
    batch_size: int = 100,
    stale_only: bool = True,
) -> int:
    if not embedding_service.is_available():
        return 0

    stmt = select(DocumentChunk).order_by(DocumentChunk.ingested_at.asc())
    result = await session.execute(stmt)
    chunks = result.scalars().all()
    if stale_only:
        chunks = [chunk for chunk in chunks if _needs_reembedding(chunk)]
    chunks = chunks[:batch_size]
    embedded = await apply_embeddings_to_chunks(chunks)
    await session.flush()
    logger.info(
        "knowledge_embedding_backfill_batch",
        requested=batch_size,
        embedded=embedded,
        stale_only=stale_only,
    )
    return embedded


def _needs_reembedding(chunk: DocumentChunk) -> bool:
    metadata = chunk.chunk_metadata or {}
    return (
        chunk.embedding is None
        or chunk.embedding_model != settings.knowledge_embedding_model
        or metadata.get("embedding_version") != settings.knowledge_embedding_version
    )


embedding_service = EmbeddingService()
