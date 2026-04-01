from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.application import adk_agent
from app.interfaces.api.app import create_app


def test_build_instruction_mentions_selected_shipment():
    context = SimpleNamespace(state={adk_agent.SELECTED_SHIPMENT_STATE_KEY: "ship-001"})

    instruction = adk_agent.build_instruction(context)

    assert "ship-001" in instruction
    assert "follow-up" in instruction.lower()


def test_build_instruction_prefers_supporting_context_for_mixed_questions():
    instruction = adk_agent.build_instruction(None)

    assert "Prefer search_supporting_context" in instruction
    assert "what is happening at the port?" in instruction
    assert "partial failures" in instruction


def test_build_instruction_mentions_cached_tool_route():
    context = SimpleNamespace(
        state={
            adk_agent.CACHED_TOOL_NAME_STATE_KEY: "get_shipment_status",
            adk_agent.CACHED_TOOL_ARGS_STATE_KEY: {"shipment_id": "ship-001"},
        }
    )

    instruction = adk_agent.build_instruction(context)

    assert "Redis plan-cache hit" in instruction
    assert "get_shipment_status" in instruction


@pytest.mark.anyio
async def test_get_shipment_status_remembers_selected_shipment(monkeypatch):
    async def fake_with_session(callback):
        return await callback("fake-session")

    async def fake_get_status(session, shipment_id):
        assert session == "fake-session"
        assert shipment_id == "ship-002"
        return {"shipment_id": shipment_id}

    monkeypatch.setattr(adk_agent, "_with_session", fake_with_session)
    monkeypatch.setattr(adk_agent.agent_tools, "get_shipment_status", fake_get_status)

    tool_context = SimpleNamespace(state={})
    result = await adk_agent.get_shipment_status("ship-002", tool_context=tool_context)

    assert result["shipment_id"] == "ship-002"
    assert tool_context.state[adk_agent.SELECTED_SHIPMENT_STATE_KEY] == "ship-002"


@pytest.mark.anyio
async def test_search_supporting_context_uses_selected_shipment(monkeypatch):
    async def fake_with_session(callback):
        return await callback("fake-session")

    async def fake_search_supporting_context(
        session,
        query,
        shipment_id=None,
        topics=None,
        top_k=5,
        web_top_k=5,
    ):
        assert session == "fake-session"
        assert query == "why is lagos congested"
        assert shipment_id == "ship-003"
        assert topics == ["congestion"]
        assert top_k == 4
        assert web_top_k == 3
        return {"knowledge_base": {"snippets": []}, "web_search": {"results": []}}

    monkeypatch.setattr(adk_agent, "_with_session", fake_with_session)
    monkeypatch.setattr(adk_agent.agent_tools, "search_supporting_context", fake_search_supporting_context)

    tool_context = SimpleNamespace(state={adk_agent.SELECTED_SHIPMENT_STATE_KEY: "ship-003"})
    result = await adk_agent.search_supporting_context(
        "why is lagos congested",
        topics=["congestion"],
        top_k=4,
        web_top_k=3,
        tool_context=tool_context,
    )

    assert result["knowledge_base"] == {"snippets": []}
    assert result["web_search"] == {"results": []}


def test_agent_factory_exposes_expected_tools():
    llm_agent = adk_agent.build_llm_agent()
    tool_names = {tool.name for tool in llm_agent.tools}

    assert tool_names == {
        "search_supporting_context",
        "web_search",
        "get_eta_revisions",
        "get_port_context",
        "list_shipments",
        "get_shipment_status",
        "get_shipment_history",
        "get_vessel_position",
        "search_knowledge_base",
        "get_clearance_checklist",
        "get_realistic_eta",
        "get_demurrage_exposure",
        "compare_shipments",
        "detect_vessel_anomaly",
        "check_vessel_swap",
    }


def test_tool_context_state_handles_missing_context():
    assert adk_agent._tool_context_state(None) == {}


@pytest.mark.anyio
async def test_get_shipment_status_emits_audit_events(monkeypatch):
    async def fake_with_session(callback):
        return await callback("fake-session")

    async def fake_get_status(session, shipment_id):
        assert session == "fake-session"
        assert shipment_id == "ship-002"
        return {"shipment_id": shipment_id, "status": "open"}

    audit_events = []

    async def fake_append_audit_event(payload):
        audit_events.append(payload)

    monkeypatch.setattr(adk_agent, "_with_session", fake_with_session)
    monkeypatch.setattr(adk_agent.agent_tools, "get_shipment_status", fake_get_status)
    monkeypatch.setattr(adk_agent, "append_audit_event", fake_append_audit_event)

    tool_context = SimpleNamespace(state={
        adk_agent.REQUEST_RUN_ID_STATE_KEY: "run-1",
        adk_agent.REQUEST_THREAD_ID_STATE_KEY: "thread-1",
        adk_agent.REQUEST_USER_ID_STATE_KEY: "user-1",
        adk_agent.REQUEST_INTENT_KIND_STATE_KEY: "shipment_location",
    })
    result = await adk_agent.get_shipment_status("ship-002", tool_context=tool_context)

    assert result["shipment_id"] == "ship-002"
    assert [event["stage"] for event in audit_events] == ["started", "completed"]
    assert audit_events[-1]["result"]["summary"]["shipment_id"] == "ship-002"


def test_database_session_db_url_keeps_async_driver(monkeypatch):
    monkeypatch.setattr(
        adk_agent,
        "settings",
        SimpleNamespace(
            adk_session_db_url="postgresql+asyncpg://postgres:secret@localhost:5432/dockie_copilot",
            database_url="postgresql+asyncpg://postgres:secret@localhost:5432/dockie_copilot",
        ),
    )

    assert (
        adk_agent._database_session_db_url()
        == "postgresql+asyncpg://postgres:secret@localhost:5432/dockie_copilot"
    )


def test_database_session_db_url_upgrades_sync_postgres_url(monkeypatch):
    monkeypatch.setattr(
        adk_agent,
        "settings",
        SimpleNamespace(
            adk_session_db_url="postgresql://postgres:secret@localhost:5432/dockie_copilot",
            database_url="postgresql+asyncpg://postgres:secret@localhost:5432/dockie_copilot",
        ),
    )

    assert (
        adk_agent._database_session_db_url()
        == "postgresql+asyncpg://postgres:secret@localhost:5432/dockie_copilot"
    )


def test_create_app_registers_agent_run_endpoint():
    app = create_app()
    route_paths = {route.path for route in app.routes}

    assert "/agent/run" in route_paths
    assert "/agent/agents/state" in route_paths
