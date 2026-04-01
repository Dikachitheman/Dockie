from __future__ import annotations

import asyncio

import pytest

from app.application import agent_tools


@pytest.mark.anyio
async def test_search_supporting_context_returns_both_parallel_results(monkeypatch):
    async def fake_search_knowledge_base(session, query, shipment_id=None, top_k=5):
        assert session == "fake-session"
        assert query == "lagos congestion"
        assert shipment_id == "ship-007"
        assert top_k == 4
        return {
            "query": query,
            "shipment_id": shipment_id,
            "snippets": [{"source_name": "shipment_events"}],
            "retrieved_at": "2026-03-30T10:00:00Z",
        }

    async def fake_web_search(query, topics=None, top_k=5):
        assert query == "lagos congestion"
        assert topics == ["port_congestion"]
        assert top_k == 3
        return {
            "query": query,
            "topics": topics,
            "results": [{"source_id": "nigeria-port-watch"}],
            "retrieved_at": "2026-03-30T10:00:01Z",
        }

    monkeypatch.setattr(agent_tools, "search_knowledge_base", fake_search_knowledge_base)
    monkeypatch.setattr(agent_tools, "web_search", fake_web_search)

    result = await agent_tools.search_supporting_context(
        "fake-session",
        query="lagos congestion",
        shipment_id="ship-007",
        topics=["port_congestion"],
        top_k=4,
        web_top_k=3,
    )

    assert result["knowledge_base"]["snippets"] == [{"source_name": "shipment_events"}]
    assert result["web_search"]["results"] == [{"source_id": "nigeria-port-watch"}]
    assert result["partial_failures"] == []


@pytest.mark.anyio
async def test_search_supporting_context_starts_knowledge_and_web_work_without_serial_blocking(monkeypatch):
    started = {"knowledge": False, "web": False}
    release = asyncio.Event()
    knowledge_started = asyncio.Event()
    web_started = asyncio.Event()

    async def fake_search_knowledge_base(session, query, shipment_id=None, top_k=5):
        del session, query, shipment_id, top_k
        started["knowledge"] = True
        knowledge_started.set()
        await release.wait()
        return {
            "query": "lagos congestion",
            "shipment_id": "ship-007",
            "snippets": [{"source_name": "shipment_events"}],
            "retrieved_at": "2026-03-30T10:00:00Z",
        }

    async def fake_web_search(query, topics=None, top_k=5):
        del query, topics, top_k
        started["web"] = True
        web_started.set()
        await release.wait()
        return {
            "query": "lagos congestion",
            "topics": ["port_congestion"],
            "results": [{"source_id": "nigeria-port-watch"}],
            "retrieved_at": "2026-03-30T10:00:01Z",
        }

    monkeypatch.setattr(agent_tools, "search_knowledge_base", fake_search_knowledge_base)
    monkeypatch.setattr(agent_tools, "web_search", fake_web_search)

    task = asyncio.create_task(
        agent_tools.search_supporting_context(
            "fake-session",
            query="lagos congestion",
            shipment_id="ship-007",
            topics=["port_congestion"],
        )
    )
    await asyncio.wait_for(asyncio.gather(knowledge_started.wait(), web_started.wait()), timeout=1)

    assert started == {"knowledge": True, "web": True}

    release.set()
    result = await task

    assert list(result.keys()) == [
        "query",
        "shipment_id",
        "topics",
        "knowledge_base",
        "web_search",
        "partial_failures",
        "retrieved_at",
    ]
    assert result["knowledge_base"]["snippets"] == [{"source_name": "shipment_events"}]
    assert result["web_search"]["results"] == [{"source_id": "nigeria-port-watch"}]


@pytest.mark.anyio
async def test_search_supporting_context_tolerates_web_failure(monkeypatch):
    async def fake_search_knowledge_base(session, query, shipment_id=None, top_k=5):
        return {
            "query": query,
            "shipment_id": shipment_id,
            "snippets": [{"source_name": "shipment_events"}],
            "retrieved_at": "2026-03-30T10:00:00Z",
        }

    async def fake_web_search(query, topics=None, top_k=5):
        raise RuntimeError("remote web timeout")

    monkeypatch.setattr(agent_tools, "search_knowledge_base", fake_search_knowledge_base)
    monkeypatch.setattr(agent_tools, "web_search", fake_web_search)

    result = await agent_tools.search_supporting_context(
        "fake-session",
        query="lagos congestion",
        shipment_id="ship-007",
        topics=["port_congestion"],
    )

    assert result["knowledge_base"]["snippets"] == [{"source_name": "shipment_events"}]
    assert result["web_search"]["results"] == []
    assert result["web_search"]["error"] == "web_search_unavailable"
    assert result["partial_failures"] == [{"source": "web_search", "error": "remote web timeout"}]
