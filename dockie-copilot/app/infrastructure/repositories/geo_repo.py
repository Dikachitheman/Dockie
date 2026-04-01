"""
GeoRepository - PostGIS spatial queries for vessel proximity and port lookups.

Uses ST_DWithin, ST_Distance, ST_DistanceSphere for real geospatial queries
powered by PostGIS, not application-level math.
"""

from __future__ import annotations

from typing import Sequence

from geoalchemy2.functions import ST_DWithin, ST_DistanceSphere, ST_MakePoint, ST_SetSRID
from sqlalchemy import Float, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import LatestPosition, ReferencePort


# 1 nautical mile in meters
NM_TO_METERS = 1852.0


class GeoRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_vessels_within_radius(
        self,
        latitude: float,
        longitude: float,
        radius_nm: float = 50.0,
        limit: int = 20,
    ) -> list[dict]:
        """
        Find all vessels with latest positions within `radius_nm` nautical miles
        of the given point. Uses PostGIS ST_DWithin for index-accelerated search.
        """
        center = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
        radius_meters = radius_nm * NM_TO_METERS

        distance_expr = ST_DistanceSphere(LatestPosition.geom, center)

        stmt = (
            select(
                LatestPosition,
                cast(distance_expr / NM_TO_METERS, Float).label("distance_nm"),
            )
            .where(
                LatestPosition.geom.isnot(None),
                ST_DWithin(
                    cast(LatestPosition.geom, geoalchemy2_Geometry()),
                    cast(center, geoalchemy2_Geometry()),
                    radius_meters,
                    use_spheroid=False,
                ),
            )
            .order_by(distance_expr)
            .limit(limit)
        )

        result = await self._session.execute(stmt)
        rows = result.all()

        return [
            {
                "mmsi": pos.mmsi,
                "imo": pos.imo,
                "vessel_name": pos.vessel_name,
                "latitude": pos.latitude,
                "longitude": pos.longitude,
                "sog_knots": pos.sog_knots,
                "cog_degrees": pos.cog_degrees,
                "navigation_status": pos.navigation_status,
                "destination_text": pos.destination_text,
                "source": pos.source,
                "observed_at": pos.observed_at.isoformat() if pos.observed_at else None,
                "distance_nm": round(distance_nm, 2) if distance_nm else None,
            }
            for pos, distance_nm in rows
        ]

    async def find_nearest_port(
        self,
        latitude: float,
        longitude: float,
        limit: int = 3,
    ) -> list[dict]:
        """
        Find the nearest reference ports to a given coordinate.
        Uses PostGIS ST_DistanceSphere for great-circle distance.
        """
        point = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
        distance_expr = ST_DistanceSphere(ReferencePort.geom, point)

        stmt = (
            select(
                ReferencePort,
                cast(distance_expr / NM_TO_METERS, Float).label("distance_nm"),
            )
            .order_by(distance_expr)
            .limit(limit)
        )

        result = await self._session.execute(stmt)
        rows = result.all()

        return [
            {
                "locode": port.locode,
                "name": port.name,
                "country": port.country,
                "latitude": port.latitude,
                "longitude": port.longitude,
                "port_type": port.port_type,
                "geofence_radius_nm": port.geofence_radius_nm,
                "distance_nm": round(distance_nm, 2) if distance_nm else None,
            }
            for port, distance_nm in rows
        ]

    async def check_port_proximity(
        self,
        latitude: float,
        longitude: float,
    ) -> dict | None:
        """
        Check if the given position is within any port's geofence radius.
        Returns the port details + distance if inside a geofence, else None.
        Uses PostGIS ST_DWithin with each port's configured geofence_radius_nm.
        """
        point = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
        distance_expr = ST_DistanceSphere(ReferencePort.geom, point)

        # Use a raw SQL approach for the dynamic radius comparison
        stmt = (
            select(
                ReferencePort,
                cast(distance_expr / NM_TO_METERS, Float).label("distance_nm"),
            )
            .where(
                distance_expr <= ReferencePort.geofence_radius_nm * NM_TO_METERS
            )
            .order_by(distance_expr)
            .limit(1)
        )

        result = await self._session.execute(stmt)
        row = result.first()

        if row is None:
            return None

        port, distance_nm = row
        return {
            "within_geofence": True,
            "locode": port.locode,
            "name": port.name,
            "country": port.country,
            "port_latitude": port.latitude,
            "port_longitude": port.longitude,
            "geofence_radius_nm": port.geofence_radius_nm,
            "distance_nm": round(distance_nm, 2) if distance_nm else None,
            "proximity_status": _proximity_label(distance_nm, port.geofence_radius_nm),
        }

    async def get_vessel_port_proximity(
        self,
        mmsi: str,
    ) -> dict | None:
        """
        Check if a specific vessel (by MMSI) is near any reference port.
        Combines latest position lookup with port proximity check.
        """
        pos_result = await self._session.execute(
            select(LatestPosition).where(LatestPosition.mmsi == mmsi)
        )
        pos = pos_result.scalar_one_or_none()
        if pos is None:
            return None

        proximity = await self.check_port_proximity(pos.latitude, pos.longitude)
        nearest = await self.find_nearest_port(pos.latitude, pos.longitude, limit=1)

        return {
            "mmsi": pos.mmsi,
            "imo": pos.imo,
            "vessel_name": pos.vessel_name,
            "latitude": pos.latitude,
            "longitude": pos.longitude,
            "observed_at": pos.observed_at.isoformat() if pos.observed_at else None,
            "port_proximity": proximity,
            "nearest_port": nearest[0] if nearest else None,
        }

    async def list_reference_ports(self) -> list[dict]:
        """Return all reference ports."""
        result = await self._session.execute(
            select(ReferencePort).order_by(ReferencePort.country, ReferencePort.name)
        )
        return [
            {
                "locode": p.locode,
                "name": p.name,
                "country": p.country,
                "latitude": p.latitude,
                "longitude": p.longitude,
                "port_type": p.port_type,
                "geofence_radius_nm": p.geofence_radius_nm,
            }
            for p in result.scalars().all()
        ]


def _proximity_label(distance_nm: float, geofence_radius_nm: float) -> str:
    if distance_nm <= 1.0:
        return "at_port"
    if distance_nm <= geofence_radius_nm * 0.5:
        return "approaching"
    return "near_port"


def geoalchemy2_Geometry():
    """Helper to get the Geography cast type for ST_DWithin."""
    from geoalchemy2.types import Geography
    return Geography(srid=4326)
