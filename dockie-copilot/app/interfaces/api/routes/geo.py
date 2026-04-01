"""
Geospatial API routes — PostGIS-powered spatial queries.

Endpoints for nearby vessel search, nearest port lookup, and port proximity detection.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services import GeoService
from app.infrastructure.database import get_db
from app.schemas.responses import (
    NearbyVesselsResponseSchema,
    NearestPortResponseSchema,
    ReferencePortSchema,
    VesselPortProximitySchema,
)

router = APIRouter(prefix="/geo", tags=["geospatial"])


@router.get("/nearby-vessels", response_model=NearbyVesselsResponseSchema)
async def find_nearby_vessels(
    latitude: float = Query(..., ge=-90, le=90, description="Center latitude"),
    longitude: float = Query(..., ge=-180, le=180, description="Center longitude"),
    radius_nm: float = Query(50.0, ge=0.1, le=500, description="Search radius in nautical miles"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Find all vessels within a radius of a given point.
    Uses PostGIS ST_DWithin for index-accelerated spatial search.
    """
    svc = GeoService(db)
    return await svc.find_nearby_vessels(latitude, longitude, radius_nm=radius_nm, limit=limit)


@router.get("/nearest-port", response_model=NearestPortResponseSchema)
async def find_nearest_port(
    latitude: float = Query(..., ge=-90, le=90, description="Query latitude"),
    longitude: float = Query(..., ge=-180, le=180, description="Query longitude"),
    limit: int = Query(3, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
):
    """
    Find the nearest reference ports to a given coordinate.
    Uses PostGIS ST_DistanceSphere for accurate great-circle distance.
    """
    svc = GeoService(db)
    return await svc.find_nearest_port(latitude, longitude, limit=limit)


@router.get("/vessel-proximity/{mmsi}")
async def get_vessel_port_proximity(
    mmsi: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Check if a vessel is near or at any reference port.
    Returns nearest port + geofence status for the vessel's latest position.
    """
    svc = GeoService(db)
    result = await svc.check_vessel_port_proximity(mmsi)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No position found for MMSI '{mmsi}'")
    return result


@router.get("/shipment-proximity/{shipment_id}")
async def get_shipment_port_proximity(
    shipment_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Check port proximity for all candidate vessels of a shipment.
    Useful for detecting arrival at discharge port.
    """
    svc = GeoService(db)
    result = await svc.check_shipment_port_proximity(shipment_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Shipment '{shipment_id}' not found")
    return result


@router.get("/reference-ports", response_model=list[ReferencePortSchema])
async def list_reference_ports(
    db: AsyncSession = Depends(get_db),
):
    """List all reference ports with coordinates."""
    svc = GeoService(db)
    return await svc.list_reference_ports()
