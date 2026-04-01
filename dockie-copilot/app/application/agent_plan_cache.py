from __future__ import annotations

import hashlib
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.cache import get_cache_backend

logger = get_logger(__name__)
settings = get_settings()

SUPPORTED_INTENT_TOOLS: dict[str, str] = {
    "shipment_location": "get_shipment_status",
    "eta_check": "get_realistic_eta",
    "demurrage_check": "get_demurrage_exposure",
    "evidence_review": "search_knowledge_base",
}


def _cache_key(*, user_id: str, shipment_id: str, intent_kind: str) -> str:
    digest = hashlib.sha1(f"{user_id}|{shipment_id}|{intent_kind}".encode("utf-8")).hexdigest()
    return f"agent_plan:{digest}"


def build_cached_tool_args(
    *,
    shipment_id: str,
    intent_kind: str,
    prompt: str,
) -> dict[str, Any] | None:
    if intent_kind == "shipment_location":
        return {"shipment_id": shipment_id}
    if intent_kind == "eta_check":
        return {"shipment_id": shipment_id}
    if intent_kind == "demurrage_check":
        return {"shipment_id": shipment_id}
    if intent_kind == "evidence_review":
        return {"shipment_id": shipment_id, "query": prompt, "top_k": 5}
    return None


async def get_cached_tool_plan(
    *,
    user_id: str,
    shipment_id: str | None,
    intent_kind: str,
) -> dict[str, Any] | None:
    if not shipment_id or intent_kind not in SUPPORTED_INTENT_TOOLS:
        return None

    try:
        return await get_cache_backend().get_json(
            _cache_key(user_id=user_id, shipment_id=shipment_id, intent_kind=intent_kind)
        )
    except Exception as exc:
        logger.warning(
            "agent_plan_cache_read_failed",
            shipment_id=shipment_id,
            intent_kind=intent_kind,
            error=str(exc),
        )
        return None


async def set_cached_tool_plan(
    *,
    user_id: str,
    shipment_id: str | None,
    intent_kind: str,
    tool_name: str,
    tool_args: dict[str, Any],
) -> None:
    if not shipment_id or intent_kind not in SUPPORTED_INTENT_TOOLS:
        return

    if SUPPORTED_INTENT_TOOLS[intent_kind] != tool_name:
        return

    try:
        await get_cache_backend().set_json(
            _cache_key(user_id=user_id, shipment_id=shipment_id, intent_kind=intent_kind),
            {
                "tool_name": tool_name,
                "tool_args": tool_args,
                "intent_kind": intent_kind,
                "shipment_id": shipment_id,
            },
            ttl_seconds=settings.agent_plan_cache_ttl_seconds,
        )
    except Exception as exc:
        logger.warning(
            "agent_plan_cache_write_failed",
            shipment_id=shipment_id,
            intent_kind=intent_kind,
            tool_name=tool_name,
            error=str(exc),
        )
