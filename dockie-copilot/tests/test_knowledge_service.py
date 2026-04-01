from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.application import services as services_module
from app.application.services import KnowledgeBaseService


@pytest.mark.anyio
async def test_knowledge_search_prioritizes_matching_shipment_evidence():
    service = KnowledgeBaseService(session=SimpleNamespace(execute=None))  # type: ignore[arg-type]
    shipment = SimpleNamespace(
        id="ship-001",
        evidence_items=[
            SimpleNamespace(
                source="carrier_schedule",
                claim="Carrier schedule declared Lagos ETA with moderate confidence.",
                captured_at=datetime.now(timezone.utc),
            )
        ],
    )

    async def fake_get_by_id(shipment_id: str):
        assert shipment_id == "ship-001"
        return shipment

    async def fake_get_all_health():
        return []

    class FakeExecuteResult:
        def scalars(self):
            return self

        def all(self):
            return []

    async def fake_execute(statement):
        del statement
        return FakeExecuteResult()

    async def fake_list_for_shipment(shipment_id: str, limit: int = 10):
        assert shipment_id == "ship-001"
        assert limit == 10
        return []

    service._shipment_repo.get_by_id = fake_get_by_id  # type: ignore[method-assign]
    service._source_health_repo.get_all = fake_get_all_health  # type: ignore[method-assign]
    service._session.execute = fake_execute  # type: ignore[attr-defined]

    result = await service.search("eta lagos confidence", shipment_id="ship-001")

    assert result.snippets
    assert result.snippets[0].source_type == "shipment_evidence"
    assert "Lagos ETA" in result.snippets[0].content


@pytest.mark.anyio
async def test_knowledge_search_uses_vector_ranked_document_chunks(monkeypatch):
    service = KnowledgeBaseService(session=SimpleNamespace(execute=None))  # type: ignore[arg-type]

    async def fake_vector_ranked_chunks(query: str, *, shipment_id: str | None):
        assert query == "customs process lagos"
        assert shipment_id is None
        return [
            SimpleNamespace(
                source_name="naija_customs_guide",
                source_type="reference_doc",
                title="Nigeria Customs Process Guide",
                content="A semantic explanation of customs processing for Lagos imports.",
                shipment_id=None,
            )
        ]

    async def fake_lexical_chunks(*, shipment_id: str | None):
        return []

    async def fake_get_all_health():
        return []

    monkeypatch.setattr(services_module, "list_source_readiness", lambda: [])
    service._vector_ranked_chunks = fake_vector_ranked_chunks  # type: ignore[method-assign]
    service._lexical_chunks = fake_lexical_chunks  # type: ignore[method-assign]
    service._source_health_repo.get_all = fake_get_all_health  # type: ignore[method-assign]

    result = await service.search("customs process lagos")

    assert result.snippets
    doc_snippet = result.snippets[0]
    assert doc_snippet.metadata["retrieval_mode"] == "vector"
    assert doc_snippet.metadata["semantic_score"] is not None
    assert doc_snippet.metadata["source_weight"] > 0
    assert "customs processing" in doc_snippet.content.lower()


@pytest.mark.anyio
async def test_knowledge_search_falls_back_to_lexical_document_chunks(monkeypatch):
    service = KnowledgeBaseService(session=SimpleNamespace(execute=None))  # type: ignore[arg-type]

    async def fake_vector_ranked_chunks(query: str, *, shipment_id: str | None):
        return []

    async def fake_lexical_chunks(*, shipment_id: str | None):
        return [
            SimpleNamespace(
                source_name="generated_analyst_docs",
                source_type="analyst_note",
                title="Lagos Congestion Summary",
                content="A lexical fallback note about anchorage queue pressure in Lagos.",
                shipment_id=None,
            )
        ]

    async def fake_get_all_health():
        return []

    monkeypatch.setattr(services_module, "list_source_readiness", lambda: [])
    service._vector_ranked_chunks = fake_vector_ranked_chunks  # type: ignore[method-assign]
    service._lexical_chunks = fake_lexical_chunks  # type: ignore[method-assign]
    service._source_health_repo.get_all = fake_get_all_health  # type: ignore[method-assign]

    result = await service.search("lagos congestion queue")

    assert result.snippets
    doc_snippet = result.snippets[0]
    assert doc_snippet.metadata["retrieval_mode"] == "lexical"
    assert "fallback" in doc_snippet.content.lower()


@pytest.mark.anyio
async def test_knowledge_search_handles_semantic_phrasing_for_vessel_motion(monkeypatch):
    service = KnowledgeBaseService(session=SimpleNamespace(execute=None))  # type: ignore[arg-type]

    async def fake_vector_ranked_chunks(query: str, *, shipment_id: str | None):
        assert query == "is the vessel moving normally?"
        return [
            SimpleNamespace(
                source_name="generated_analyst_docs",
                source_type="analyst_doc",
                title="Navigation health note",
                content="navigation_status under_way_using_engine with steady sog_knots and no anomaly flags.",
                shipment_id="ship-001",
            )
        ]

    async def fake_lexical_chunks(*, shipment_id: str | None):
        return []

    async def fake_get_all_health():
        return []

    shipment = SimpleNamespace(
        id="ship-001",
        evidence_items=[],
        candidate_vessels=[],
        discharge_port="NGLAG",
    )

    async def fake_get_by_id(shipment_id: str):
        assert shipment_id == "ship-001"
        return shipment

    class FakeExecuteResult:
        def scalars(self):
            return self

        def all(self):
            return []

    async def fake_execute(statement):
        del statement
        return FakeExecuteResult()

    async def fake_list_for_shipment(shipment_id: str, limit: int = 10):
        assert shipment_id == "ship-001"
        assert limit == 10
        return []

    monkeypatch.setattr(services_module, "list_source_readiness", lambda: [])
    service._vector_ranked_chunks = fake_vector_ranked_chunks  # type: ignore[method-assign]
    service._lexical_chunks = fake_lexical_chunks  # type: ignore[method-assign]
    service._source_health_repo.get_all = fake_get_all_health  # type: ignore[method-assign]
    service._shipment_repo.get_by_id = fake_get_by_id  # type: ignore[method-assign]
    service._revision_repo.list_for_shipment = fake_list_for_shipment  # type: ignore[method-assign]
    service._session.execute = fake_execute  # type: ignore[attr-defined]

    result = await service.search("is the vessel moving normally?", shipment_id="ship-001")

    assert result.snippets
    top = result.snippets[0]
    assert top.metadata["retrieval_mode"] == "vector"
    assert "under_way_using_engine" in top.content
