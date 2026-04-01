from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.infrastructure import agent_audit


def test_infer_intent_kind_detects_location_question():
    assert agent_audit.infer_intent_kind("Where is this shipment now?") == "shipment_location"


def test_summarize_tool_output_truncates_large_strings():
    summary = agent_audit.summarize_tool_output({"message": "x" * 500, "status": "ok"})

    assert "message" in summary["summary"]
    assert summary["summary"]["message"].endswith("...")
    assert summary["summary"]["status"] == "ok"


@pytest.mark.anyio
async def test_append_audit_event_writes_jsonl(tmp_path, monkeypatch):
    log_path = tmp_path / "agent_runs.jsonl"
    monkeypatch.setattr(
        agent_audit,
        "settings",
        SimpleNamespace(agent_audit_log_enabled=True, agent_audit_log_path=str(log_path)),
    )

    await agent_audit.append_audit_event({"event_type": "run_started", "run_id": "run-123"})

    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert payload["event_type"] == "run_started"
    assert payload["run_id"] == "run-123"
    assert "logged_at" in payload
