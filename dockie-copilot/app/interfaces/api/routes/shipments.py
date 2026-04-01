"""
Shipment API routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services import ShipmentService
from app.infrastructure.database import get_db
from app.schemas.requests import ManualShipmentCreateRequest
from app.schemas.responses import (
    CarrierPerformanceSchema,
    DemurrageExposureSchema,
    ETARevisionSchema,
    PortCongestionSummarySchema,
    PortObservationSchema,
    ShipmentBundleSchema,
    ShipmentDetailSchema,
    ShipmentHistorySchema,
    ShipmentStatusSchema,
    ShipmentSummarySchema,
    VesselAnomalySchema,
)

router = APIRouter(prefix="/shipments", tags=["shipments"])


@router.get("", response_model=list[ShipmentSummarySchema])
async def list_shipments(db: AsyncSession = Depends(get_db)):
    """List all active shipments."""
    svc = ShipmentService(db)
    return await svc.list_shipments()


@router.post("/manual", response_model=ShipmentDetailSchema, status_code=201)
async def create_manual_shipment(
    payload: ManualShipmentCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a manual shipment tied to a vessel MMSI for live tracking."""
    svc = ShipmentService(db)
    return await svc.create_manual_shipment(payload)


# Static routes must be declared before /{shipment_id} or FastAPI's path-param
# wildcard will match them first (declaration order wins in Starlette routing).
@router.get("/carrier-performance", response_model=list[CarrierPerformanceSchema])
async def list_carrier_performance(service_lane: str | None = None, db: AsyncSession = Depends(get_db)):
    svc = ShipmentService(db)
    return await svc.list_carrier_performance(service_lane=service_lane)


@router.get("/{shipment_id}", response_model=ShipmentDetailSchema)
async def get_shipment(shipment_id: str, db: AsyncSession = Depends(get_db)):
    """Get full details for a shipment including candidate vessels and evidence."""
    svc = ShipmentService(db)
    result = await svc.get_shipment_detail(shipment_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Shipment '{shipment_id}' not found")
    return result


@router.get("/{shipment_id}/bundle", response_model=ShipmentBundleSchema)
async def get_shipment_bundle(shipment_id: str, db: AsyncSession = Depends(get_db)):
    """Get detail, status, and history in one request for shipment-focused screens."""
    svc = ShipmentService(db)
    result = await svc.get_shipment_bundle(shipment_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Shipment '{shipment_id}' not found")
    return result


@router.get("/{shipment_id}/status", response_model=ShipmentStatusSchema)
async def get_shipment_status(shipment_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get current tracking status: latest position, speed, ETA confidence, and freshness.
    This is the primary copilot endpoint.
    """
    svc = ShipmentService(db)
    result = await svc.get_shipment_status(shipment_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Shipment '{shipment_id}' not found")
    return result


@router.get("/{shipment_id}/history", response_model=ShipmentHistorySchema)
async def get_shipment_history(shipment_id: str, db: AsyncSession = Depends(get_db)):
    """Get the full position track and event log for a shipment."""
    svc = ShipmentService(db)
    result = await svc.get_shipment_history(shipment_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Shipment '{shipment_id}' not found")
    return result


@router.get("/{shipment_id}/eta-revisions", response_model=list[ETARevisionSchema])
async def get_shipment_eta_revisions(shipment_id: str, db: AsyncSession = Depends(get_db)):
    svc = ShipmentService(db)
    return await svc.get_eta_revisions(shipment_id)


@router.get("/{shipment_id}/port-context", response_model=list[PortObservationSchema])
async def get_shipment_port_context(shipment_id: str, db: AsyncSession = Depends(get_db)):
    svc = ShipmentService(db)
    return await svc.get_port_observations(shipment_id)


@router.get("/{shipment_id}/demurrage-exposure", response_model=DemurrageExposureSchema)
async def get_shipment_demurrage_exposure(shipment_id: str, db: AsyncSession = Depends(get_db)):
    svc = ShipmentService(db)
    result = await svc.get_demurrage_exposure(shipment_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Shipment '{shipment_id}' not found")
    return result


@router.get("/{shipment_id}/port-congestion", response_model=PortCongestionSummarySchema)
async def get_shipment_port_congestion(shipment_id: str, db: AsyncSession = Depends(get_db)):
    svc = ShipmentService(db)
    result = await svc.get_port_congestion_summary(shipment_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Shipment '{shipment_id}' not found")
    return result


@router.get("/{shipment_id}/vessel-anomaly", response_model=VesselAnomalySchema)
async def get_shipment_vessel_anomaly(shipment_id: str, db: AsyncSession = Depends(get_db)):
    svc = ShipmentService(db)
    result = await svc.detect_vessel_anomaly(shipment_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Shipment '{shipment_id}' not found")
    return result
