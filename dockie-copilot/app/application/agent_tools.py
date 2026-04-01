"""
Agent tool functions.

These wrap application services and return structured JSON suitable for
consumption by Google ADK or any LLM tool-calling framework.

Each function:
- returns a dict (JSON-serializable)
- includes source provenance and freshness
- surfaces confidence and uncertainty explicitly
- never executes external side effects
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services import KnowledgeBaseService, ShipmentService, SourceHealthService
from app.core.logging import get_logger
from app.infrastructure.fake_web import FakeWebClient

logger = get_logger(__name__)
fake_web_client = FakeWebClient()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_shipment_status(
    session: AsyncSession, shipment_id: str
) -> dict[str, Any]:
    """
    Tool: get_shipment_status

    Returns current position, speed, course, ETA, and freshness for a shipment.
    Designed for agent consumption — includes confidence explanation.
    """
    svc = ShipmentService(session)
    status = await svc.get_shipment_status(shipment_id)

    if status is None:
        return {
            "error": "not_found",
            "shipment_id": shipment_id,
            "message": f"No shipment found with id '{shipment_id}'",
            "retrieved_at": _now_iso(),
        }

    pos = status.latest_position
    result: dict[str, Any] = {
        "shipment_id": status.shipment_id,
        "booking_ref": status.booking_ref,
        "carrier": status.carrier,
        "status": status.status,
        "declared_eta": status.declared_eta.isoformat() if status.declared_eta else None,
        "latest_position": None,
        "eta_confidence": {
            "score": status.eta_confidence.confidence,
            "freshness": status.eta_confidence.freshness,
            "explanation": status.eta_confidence.explanation,
        },
        "candidate_vessels": [
            {
                "name": v.name,
                "imo": v.imo,
                "mmsi": v.mmsi,
                "is_primary": v.is_primary,
            }
            for v in status.candidate_vessels
        ],
        "freshness_warning": status.freshness_warning,
        "retrieved_at": _now_iso(),
    }

    if pos:
        result["latest_position"] = {
            "latitude": pos.latitude,
            "longitude": pos.longitude,
            "speed_knots": pos.sog_knots,
            "course_degrees": pos.cog_degrees,
            "heading_degrees": pos.heading_degrees,
            "navigation_status": pos.navigation_status,
            "destination": pos.destination_text,
            "observed_at": pos.observed_at.isoformat(),
            "source": pos.source,
            "vessel_name": pos.vessel_name,
        }

    return result


async def get_vessel_position(
    session: AsyncSession, mmsi: Optional[str] = None, imo: Optional[str] = None
) -> dict[str, Any]:
    """
    Tool: get_vessel_position

    Returns the latest known position for a vessel identified by MMSI or IMO.
    """
    from app.infrastructure.repositories import PositionRepository

    if not mmsi and not imo:
        return {
            "error": "bad_request",
            "message": "Either mmsi or imo must be provided",
            "retrieved_at": _now_iso(),
        }

    repo = PositionRepository(session)
    pos = None

    if mmsi:
        pos = await repo.get_latest_for_mmsi(mmsi)
    if pos is None and imo:
        pos = await repo.get_latest_for_imo(imo)

    if pos is None:
        return {
            "error": "not_found",
            "message": f"No position found for mmsi={mmsi} imo={imo}",
            "retrieved_at": _now_iso(),
        }

    return {
        "mmsi": pos.mmsi,
        "imo": pos.imo,
        "vessel_name": pos.vessel_name,
        "latitude": pos.latitude,
        "longitude": pos.longitude,
        "speed_knots": pos.sog_knots,
        "course_degrees": pos.cog_degrees,
        "navigation_status": pos.navigation_status,
        "destination": pos.destination_text,
        "observed_at": pos.observed_at.isoformat(),
        "source": pos.source,
        "retrieved_at": _now_iso(),
    }


async def get_shipment_history(
    session: AsyncSession, shipment_id: str
) -> dict[str, Any]:
    """
    Tool: get_shipment_history

    Returns the full voyage track and event log for a shipment.
    Useful for answering 'what changed since yesterday?' questions.
    """
    svc = ShipmentService(session)
    history = await svc.get_shipment_history(shipment_id)

    if history is None:
        return {
            "error": "not_found",
            "shipment_id": shipment_id,
            "message": f"No shipment found with id '{shipment_id}'",
            "retrieved_at": _now_iso(),
        }

    return {
        "shipment_id": history.shipment_id,
        "vessel_mmsi": history.vessel_mmsi,
        "vessel_name": history.vessel_name,
        "track_point_count": len(history.track),
        "track": [
            {
                "latitude": p.latitude,
                "longitude": p.longitude,
                "speed_knots": p.sog_knots,
                "course_degrees": p.cog_degrees,
                "observed_at": p.observed_at.isoformat(),
                "source": p.source,
            }
            for p in history.track
        ],
        "events": [
            {
                "type": e.event_type,
                "at": e.event_at.isoformat(),
                "details": e.details,
                "source": e.source,
            }
            for e in history.events
        ],
        "retrieved_at": _now_iso(),
    }


async def list_shipments_tool(session: AsyncSession) -> dict[str, Any]:
    """
    Tool: list_shipments

    Returns a summary list of all active shipments.
    """
    svc = ShipmentService(session)
    shipments = await svc.list_shipments()

    return {
        "shipment_count": len(shipments),
        "shipments": [
            {
                "shipment_id": s.id,
                "booking_ref": s.booking_ref,
                "carrier": s.carrier,
                "status": s.status,
                "discharge_port": s.discharge_port,
                "declared_eta": s.declared_eta_date.isoformat() if s.declared_eta_date else None,
            }
            for s in shipments
        ],
        "retrieved_at": _now_iso(),
    }


async def search_knowledge_base(
    session: AsyncSession,
    query: str,
    shipment_id: str | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """
    Tool: search_knowledge_base

    Retrieves the most relevant evidence, events, and source-policy context
    for a shipment-specific or general operational query.
    """
    svc = KnowledgeBaseService(session)
    result = await svc.search(query, shipment_id=shipment_id, top_k=top_k)
    return result.model_dump(mode="json")


async def web_search(
    query: str,
    topics: list[str] | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """
    Tool: web_search

    Searches the deployed fake-web corpus over HTTP using site search-index endpoints.
    This is remote-first and does not read site article content from the local repo.
    """
    result = await fake_web_client.search(query=query, topics=topics, limit=top_k)
    return result.model_dump(mode="json")


async def web_search_plan(
    query: str,
    topics: list[str] | None = None,
) -> dict[str, Any]:
    """
    Tool helper: web_search_plan

    Returns the source-routing plan for remote fake-web search without fetching
    remote site indexes. Intended for UI progress and source preloading.
    """
    result = await fake_web_client.plan(query=query, topics=topics)
    return result.model_dump(mode="json")


async def search_supporting_context(
    session: AsyncSession,
    query: str,
    shipment_id: str | None = None,
    topics: list[str] | None = None,
    top_k: int = 5,
    web_top_k: int = 5,
) -> dict[str, Any]:
    """
    Tool: search_supporting_context

    Runs internal knowledge retrieval and remote web search in parallel so the
    agent can gather supporting context without waiting for each source class
    serially.
    """
    knowledge_task = search_knowledge_base(
        session,
        query=query,
        shipment_id=shipment_id,
        top_k=top_k,
    )
    web_task = web_search(query=query, topics=topics, top_k=web_top_k)
    knowledge_result, web_result = await asyncio.gather(
        knowledge_task,
        web_task,
        return_exceptions=True,
    )

    partial_failures: list[dict[str, str]] = []
    if isinstance(knowledge_result, Exception):
        logger.warning(
            "search_supporting_context_knowledge_failed",
            query=query,
            shipment_id=shipment_id,
            error=str(knowledge_result),
        )
        partial_failures.append({"source": "knowledge_base", "error": str(knowledge_result)})
        knowledge_result = {
            "query": query,
            "shipment_id": shipment_id,
            "snippets": [],
            "retrieved_at": _now_iso(),
            "error": "knowledge_base_unavailable",
        }

    if isinstance(web_result, Exception):
        logger.warning(
            "search_supporting_context_web_failed",
            query=query,
            topics=topics,
            error=str(web_result),
        )
        partial_failures.append({"source": "web_search", "error": str(web_result)})
        web_result = {
            "query": query,
            "normalized_query": query.lower().strip(),
            "topics": topics or [],
            "candidate_sources": [],
            "results": [],
            "retrieved_at": _now_iso(),
            "search_mode": "remote",
            "error": "web_search_unavailable",
        }

    return {
        "query": query,
        "shipment_id": shipment_id,
        "topics": topics or [],
        "knowledge_base": knowledge_result,
        "web_search": web_result,
        "partial_failures": partial_failures,
        "retrieved_at": _now_iso(),
    }


async def get_eta_revisions(
    session: AsyncSession,
    shipment_id: str,
) -> dict[str, Any]:
    """
    Tool: get_eta_revisions

    Returns recent carrier ETA changes recorded for a shipment.
    """
    svc = ShipmentService(session)
    revisions = await svc.get_eta_revisions(shipment_id)
    return {
        "shipment_id": shipment_id,
        "revision_count": len(revisions),
        "revisions": [item.model_dump(mode="json") for item in revisions],
        "retrieved_at": _now_iso(),
    }


async def get_port_context(
    session: AsyncSession,
    shipment_id: str,
) -> dict[str, Any]:
    """
    Tool: get_port_context

    Returns recent Nigerian port observations tied to a shipment's candidate vessels.
    """
    svc = ShipmentService(session)
    observations = await svc.get_port_observations(shipment_id)
    return {
        "shipment_id": shipment_id,
        "observation_count": len(observations),
        "observations": [item.model_dump(mode="json") for item in observations],
        "retrieved_at": _now_iso(),
    }


async def get_clearance_checklist(
    session: AsyncSession,
    shipment_id: str,
) -> dict[str, Any]:
    svc = ShipmentService(session)
    checklist = await svc.get_clearance_checklist(shipment_id)
    if checklist is None:
        return {
            "error": "not_found",
            "shipment_id": shipment_id,
            "message": f"No shipment found with id '{shipment_id}'",
            "retrieved_at": _now_iso(),
        }
    return checklist.model_dump(mode="json") | {"retrieved_at": _now_iso()}


async def get_realistic_eta(
    session: AsyncSession,
    shipment_id: str,
) -> dict[str, Any]:
    svc = ShipmentService(session)
    result = await svc.get_realistic_eta(shipment_id)
    if result is None:
        return {
            "error": "not_found",
            "shipment_id": shipment_id,
            "message": f"No shipment found with id '{shipment_id}'",
            "retrieved_at": _now_iso(),
        }
    return result.model_dump(mode="json") | {"retrieved_at": _now_iso()}


async def get_demurrage_exposure(
    session: AsyncSession,
    shipment_id: str,
) -> dict[str, Any]:
    svc = ShipmentService(session)
    result = await svc.get_demurrage_exposure(shipment_id)
    if result is None:
        return {
            "error": "not_found",
            "shipment_id": shipment_id,
            "message": f"No shipment found with id '{shipment_id}'",
            "retrieved_at": _now_iso(),
        }
    return result.model_dump(mode="json") | {"retrieved_at": _now_iso()}


async def compare_shipments(
    session: AsyncSession,
    shipment_ids: list[str] | None = None,
) -> dict[str, Any]:
    svc = ShipmentService(session)
    result = await svc.compare_shipments(shipment_ids)
    return result.model_dump(mode="json") | {"retrieved_at": _now_iso()}


async def detect_vessel_anomaly(
    session: AsyncSession,
    shipment_id: str,
) -> dict[str, Any]:
    svc = ShipmentService(session)
    result = await svc.detect_vessel_anomaly(shipment_id)
    if result is None:
        return {
            "error": "not_found",
            "shipment_id": shipment_id,
            "message": f"No shipment found with id '{shipment_id}'",
            "retrieved_at": _now_iso(),
        }
    return result.model_dump(mode="json") | {"retrieved_at": _now_iso()}


async def check_vessel_swap(
    session: AsyncSession,
    shipment_id: str,
) -> dict[str, Any]:
    svc = ShipmentService(session)
    result = await svc.check_vessel_swap(shipment_id)
    if result is None:
        return {
            "error": "not_found",
            "shipment_id": shipment_id,
            "message": f"No shipment found with id '{shipment_id}'",
            "retrieved_at": _now_iso(),
        }
    return result.model_dump(mode="json") | {"retrieved_at": _now_iso()}


# ---------------------------------------------------------------------------
# PostGIS geospatial tools
# ---------------------------------------------------------------------------

async def find_nearby_vessels(
    session: AsyncSession,
    latitude: float,
    longitude: float,
    radius_nm: float = 50.0,
) -> dict[str, Any]:
    """
    Tool: find_nearby_vessels

    Finds all tracked vessels within a given radius (in nautical miles) of a
    coordinate point. Uses PostGIS ST_DWithin for index-accelerated spatial search.
    Useful for questions like "show vessels near Lagos" or "what ships are within 100nm".
    """
    from app.application.services import GeoService

    svc = GeoService(session)
    result = await svc.find_nearby_vessels(latitude, longitude, radius_nm=radius_nm)
    return result.model_dump(mode="json") | {"retrieved_at": _now_iso()}


async def find_nearest_port(
    session: AsyncSession,
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    """
    Tool: find_nearest_port

    Finds the closest reference ports to a given coordinate using PostGIS
    ST_DistanceSphere for accurate great-circle distance calculation.
    Useful for questions like "what port is closest to the vessel" or
    "which port is the ship heading to based on position".
    """
    from app.application.services import GeoService

    svc = GeoService(session)
    result = await svc.find_nearest_port(latitude, longitude, limit=3)
    return result.model_dump(mode="json") | {"retrieved_at": _now_iso()}


async def check_port_proximity(
    session: AsyncSession,
    shipment_id: Optional[str] = None,
    mmsi: Optional[str] = None,
) -> dict[str, Any]:
    """
    Tool: check_port_proximity

    Checks whether a vessel is near or has arrived at a port by comparing its
    latest position against reference port geofence boundaries using PostGIS.
    Provide either a shipment_id or a vessel MMSI.
    Returns proximity status: at_port, approaching, near_port, or not near any port.
    """
    from app.application.services import GeoService

    if not shipment_id and not mmsi:
        return {
            "error": "bad_request",
            "message": "Either shipment_id or mmsi must be provided",
            "retrieved_at": _now_iso(),
        }

    svc = GeoService(session)

    if shipment_id:
        result = await svc.check_shipment_port_proximity(shipment_id)
        if result is None:
            return {
                "error": "not_found",
                "shipment_id": shipment_id,
                "message": f"No shipment found with id '{shipment_id}'",
                "retrieved_at": _now_iso(),
            }
        return result | {"retrieved_at": _now_iso()}

    result = await svc.check_vessel_port_proximity(mmsi)
    if result is None:
        return {
            "error": "not_found",
            "mmsi": mmsi,
            "message": f"No position found for MMSI '{mmsi}'",
            "retrieved_at": _now_iso(),
        }
    return result | {"retrieved_at": _now_iso()}
