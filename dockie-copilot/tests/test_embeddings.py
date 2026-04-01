from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.infrastructure import embeddings as embeddings_module


@pytest.mark.anyio
async def test_apply_embeddings_to_chunks_sets_fields(monkeypatch):
    chunks = [
        SimpleNamespace(title="Doc 1", content="alpha", embedding=None, embedding_model=None, embedded_at=None),
        SimpleNamespace(title="Doc 2", content="beta", embedding=None, embedding_model=None, embedded_at=None),
    ]

    monkeypatch.setattr(
        embeddings_module.embedding_service,
        "is_available",
        lambda: True,
    )

    async def fake_embed_texts(texts):
        assert texts == ["Doc 1 alpha", "Doc 2 beta"]
        return [[0.1, 0.2], [0.3, 0.4]]

    monkeypatch.setattr(embeddings_module.embedding_service, "embed_texts", fake_embed_texts)

    embedded = await embeddings_module.apply_embeddings_to_chunks(chunks)

    assert embedded == 2
    assert chunks[0].embedding == [0.1, 0.2]
    assert chunks[1].embedding_model == embeddings_module.settings.knowledge_embedding_model
    assert isinstance(chunks[0].embedded_at, datetime)
    assert chunks[0].chunk_metadata["embedding_version"] == embeddings_module.settings.knowledge_embedding_version


@pytest.mark.anyio
async def test_backfill_document_chunk_embeddings_flushes_embedded_rows(monkeypatch):
    chunk = SimpleNamespace(
        title="Doc 1",
        content="alpha",
        embedding=None,
        embedding_model=None,
        embedded_at=None,
        chunk_metadata={},
        ingested_at=datetime.now(timezone.utc),
    )

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return [chunk]

    execute_calls: list[object] = []
    flush_calls = 0

    async def fake_execute(statement):
        execute_calls.append(statement)
        return FakeResult()

    async def fake_flush():
        nonlocal flush_calls
        flush_calls += 1

    session = SimpleNamespace(execute=fake_execute, flush=fake_flush)

    monkeypatch.setattr(embeddings_module.embedding_service, "is_available", lambda: True)

    async def fake_embed_texts(texts):
        return [[0.9, 0.8]]

    monkeypatch.setattr(embeddings_module.embedding_service, "embed_texts", fake_embed_texts)

    embedded = await embeddings_module.backfill_document_chunk_embeddings(session, batch_size=25)

    assert embedded == 1
    assert execute_calls
    assert flush_calls == 1
    assert chunk.embedding == [0.9, 0.8]


def test_needs_reembedding_detects_model_or_version_drift():
    chunk = SimpleNamespace(
        embedding=[0.1, 0.2],
        embedding_model=embeddings_module.settings.knowledge_embedding_model,
        chunk_metadata={"embedding_version": embeddings_module.settings.knowledge_embedding_version},
    )

    assert embeddings_module._needs_reembedding(chunk) is False

    chunk.chunk_metadata = {"embedding_version": "old-version"}
    assert embeddings_module._needs_reembedding(chunk) is True
