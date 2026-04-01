"""
Source health and agent tool routes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.application import agent_tools
from app.core.config import get_settings
from app.application.services import (
    AppBootstrapService,
    KnowledgeBaseService,
    SourceCatalogService,
    SourceHealthService,
)
from app.infrastructure.aisstream import capture_diagnostic_sample
from app.infrastructure.database import get_db
from app.interfaces.api.user_context import RequestUserContext, get_request_user_context
from app.schemas.responses import (
    AppBootstrapSchema,
    FakeWebSearchPlanResponseSchema,
    FakeWebSearchResponseSchema,
    KnowledgeSearchResponseSchema,
    ShipmentComparisonSchema,
    SourceHealthSchema,
    SourceReadinessSchema,
)

router = APIRouter(tags=["meta"])
settings = get_settings()


@router.get("/health", summary="Application health check")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Basic liveness + DB connectivity check."""
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        return {"status": "degraded", "error": str(exc)}


@router.get("/source-health", response_model=list[SourceHealthSchema], tags=["sources"])
async def source_health(db: AsyncSession = Depends(get_db)):
    """List health status for all data sources."""
    svc = SourceHealthService(db)
    return await svc.list_health()


@router.get("/app-bootstrap", response_model=AppBootstrapSchema, tags=["meta"])
async def app_bootstrap(
    user: RequestUserContext = Depends(get_request_user_context),
):
    """Return first-load app data in one round-trip for the primary frontend shell."""
    svc = AppBootstrapService()
    return await svc.get_bootstrap(user_id=user.user_id)


@router.get("/sources/readiness", response_model=list[SourceReadinessSchema], tags=["sources"])
async def source_readiness():
    """List baseline and live source readiness for the current deployment."""
    svc = SourceCatalogService()
    return await svc.list_readiness()


@router.get("/sources/aisstream/diagnostic", tags=["sources"])
async def aisstream_diagnostic(sample_size: int = 10):
    """Capture a short sample of any live AIS messages to discover active MMSIs."""
    if not settings.aisstream_api_key:
        raise HTTPException(status_code=400, detail="AISSTREAM_API_KEY is not configured.")
    try:
        result = await capture_diagnostic_sample(
            api_key=settings.aisstream_api_key,
            sample_size=max(1, min(sample_size, 25)),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AISStream diagnostic failed: {exc}") from exc

    return {
        "source": "aisstream",
        "subscribed_mode": result.subscribed_mode,
        "inspected_messages": result.inspected_messages,
        "sample_count": len(result.sample),
        "sample": result.sample,
    }


@router.get("/knowledge/search", response_model=KnowledgeSearchResponseSchema, tags=["knowledge"])
async def knowledge_search(
    query: str,
    shipment_id: str | None = None,
    top_k: int = 5,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve relevant evidence, voyage events, and source context."""
    svc = KnowledgeBaseService(db)
    return await svc.search(query=query, shipment_id=shipment_id, top_k=top_k)


@router.get("/web-search", response_model=FakeWebSearchResponseSchema, tags=["knowledge"])
async def fake_web_search(
    query: str,
    top_k: int = 5,
):
    """Search the deployed fake-web corpus over remote HTTP search-index endpoints."""
    return await agent_tools.web_search(query=query, top_k=top_k)


@router.get("/web-search/plan", response_model=FakeWebSearchPlanResponseSchema, tags=["knowledge"])
async def fake_web_search_plan(
    query: str,
):
    """Return the remote-source search plan without fetching the remote indexes."""
    return await agent_tools.web_search_plan(query=query)


# ---------------------------------------------------------------------------
# Agent tool endpoints — RESTful wrappers around agent_tools module
# ---------------------------------------------------------------------------

agent_router = APIRouter(prefix="/agent", tags=["agent-tools"])


@agent_router.get("/shipments", summary="Agent: list shipments")
async def agent_list_shipments(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await agent_tools.list_shipments_tool(db)


@agent_router.get("/shipments/{shipment_id}/status", summary="Agent: shipment status")
async def agent_shipment_status(
    shipment_id: str, 
    db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    return await agent_tools.get_shipment_status(db, shipment_id)


@agent_router.get("/shipments/{shipment_id}/history", summary="Agent: shipment history")
async def agent_shipment_history(
    shipment_id: str, 
    db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    return await agent_tools.get_shipment_history(db, shipment_id)


@agent_router.get("/shipments/{shipment_id}/eta-revisions", summary="Agent: shipment ETA revisions")
async def agent_shipment_eta_revisions(
    shipment_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await agent_tools.get_eta_revisions(db, shipment_id)


@agent_router.get("/shipments/{shipment_id}/port-context", summary="Agent: shipment port context")
async def agent_shipment_port_context(
    shipment_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await agent_tools.get_port_context(db, shipment_id)


@agent_router.get("/vessel/position", summary="Agent: vessel position")
async def agent_vessel_position(
    mmsi: str | None = None,
    imo: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await agent_tools.get_vessel_position(db, mmsi=mmsi, imo=imo)


@router.get("/shipments/compare", response_model=ShipmentComparisonSchema, tags=["shipments"])
async def compare_shipments(
    shipment_ids: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    parsed_ids = [item.strip() for item in shipment_ids.split(",")] if shipment_ids else None
    parsed_ids = [item for item in (parsed_ids or []) if item] or None
    return await agent_tools.compare_shipments(db, parsed_ids)
