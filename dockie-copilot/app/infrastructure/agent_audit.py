from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()
_write_lock = asyncio.Lock()


def infer_intent_kind(prompt: str) -> str:
    lower = prompt.lower()
    if any(term in lower for term in ("where is", "location", "position", "track", "tracking", "heading", "speed")):
        return "shipment_location"
    if any(term in lower for term in ("eta", "arrival", "arrive", "delay", "when will", "when does")):
        return "eta_check"
    if any(term in lower for term in ("evidence", "source", "confidence", "why", "what changed", "reliable")):
        return "evidence_review"
    if any(term in lower for term in ("demurrage", "free days", "storage", "clearance", "cost", "exposure")):
        return "demurrage_check"
    if any(term in lower for term in ("compare", "which shipment", "needs attention", "riskier")):
        return "shipment_comparison"
    return "general_follow_up"


def truncate_text(value: str | None, limit: int = 800) -> str | None:
    if value is None:
        return None
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit].rstrip()}..."


def summarize_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 3:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return truncate_text(value, limit=300)
    if isinstance(value, list):
        preview = [summarize_value(item, depth=depth + 1) for item in value[:5]]
        if len(value) > 5:
            preview.append(f"<+{len(value) - 5} more>")
        return preview
    if isinstance(value, dict):
        summary: dict[str, Any] = {}
        for key, item in list(value.items())[:12]:
            summary[str(key)] = summarize_value(item, depth=depth + 1)
        if len(value) > 12:
            summary["_truncated_keys"] = len(value) - 12
        return summary
    if hasattr(value, "model_dump"):
        return summarize_value(value.model_dump(), depth=depth + 1)
    if hasattr(value, "__dict__"):
        return summarize_value(vars(value), depth=depth + 1)
    return truncate_text(repr(value), limit=300)


def summarize_tool_output(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return {
            "keys": sorted(result.keys()),
            "summary": summarize_value(result),
        }
    if isinstance(result, list):
        return {
            "length": len(result),
            "summary": summarize_value(result),
        }
    return {"summary": summarize_value(result)}


def _log_path() -> Path:
    return Path(settings.agent_audit_log_path)


async def append_audit_event(event: dict[str, Any]) -> None:
    if not settings.agent_audit_log_enabled:
        return

    payload = {
        "logged_at": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    path = _log_path()
    try:
        async with _write_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=True, default=str))
                handle.write("\n")
    except Exception as exc:
        logger.warning("agent_audit_write_failed", error=str(exc), path=str(path))
