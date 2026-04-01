"""
PositionRepository - async SQLAlchemy data access for vessel positions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from geoalchemy2.functions import ST_MakePoint, ST_SetSRID
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import LatestPosition, Position


@dataclass(slots=True)
class PositionSaveResult:
    position: Position | LatestPosition
    status: str


class PositionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest_for_mmsi(self, mmsi: str) -> Optional[LatestPosition]:
        result = await self._session.execute(
            select(LatestPosition).where(LatestPosition.mmsi == mmsi)
        )
        return result.scalar_one_or_none()

    async def get_latest_for_imo(self, imo: str) -> Optional[LatestPosition]:
        result = await self._session.execute(
            select(LatestPosition)
            .where(LatestPosition.imo == imo)
            .order_by(LatestPosition.observed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_for_mmsis(
        self, mmsis: Sequence[str]
    ) -> dict[str, LatestPosition]:
        return await self._get_latest_by_identifier(LatestPosition.mmsi, mmsis)

    async def get_latest_for_imos(
        self, imos: Sequence[str]
    ) -> dict[str, LatestPosition]:
        return await self._get_latest_by_identifier(LatestPosition.imo, imos)

    async def get_history_for_mmsi(
        self, mmsi: str, limit: int = 100
    ) -> Sequence[Position]:
        result = await self._session.execute(
            select(Position)
            .where(Position.mmsi == mmsi)
            .order_by(Position.observed_at.asc())
            .limit(limit)
        )
        return result.scalars().all()

    async def save(self, position: Position) -> Position:
        result = await self.save_with_status(position)
        return result.position

    async def save_with_status(self, position: Position) -> PositionSaveResult:
        if position.latitude is not None and position.longitude is not None:
            geom = ST_SetSRID(ST_MakePoint(position.longitude, position.latitude), 4326)
            position.geom = geom
        else:
            geom = None

        current = await self.get_latest_for_mmsi(position.mmsi)

        self._session.add(position)
        await self._session.flush()

        await self._session.execute(
            insert(LatestPosition)
            .values(
                mmsi=position.mmsi,
                imo=position.imo,
                vessel_name=position.vessel_name,
                latitude=position.latitude,
                longitude=position.longitude,
                geom=geom,
                sog_knots=position.sog_knots,
                cog_degrees=position.cog_degrees,
                heading_degrees=position.heading_degrees,
                navigation_status=position.navigation_status,
                destination_text=position.destination_text,
                source=position.source,
                observed_at=position.observed_at,
                raw_event_id=position.raw_event_id,
            )
            .on_conflict_do_update(
                index_elements=[LatestPosition.mmsi],
                set_={
                    "imo": position.imo,
                    "vessel_name": position.vessel_name,
                    "latitude": position.latitude,
                    "longitude": position.longitude,
                    "geom": geom,
                    "sog_knots": position.sog_knots,
                    "cog_degrees": position.cog_degrees,
                    "heading_degrees": position.heading_degrees,
                    "navigation_status": position.navigation_status,
                    "destination_text": position.destination_text,
                    "source": position.source,
                    "observed_at": position.observed_at,
                    "raw_event_id": position.raw_event_id,
                    "updated_at": func.now(),
                },
                where=LatestPosition.observed_at < position.observed_at,
            )
        )

        if current:
            if current.observed_at == position.observed_at:
                return PositionSaveResult(position=current, status="already_current")
            if current.observed_at > position.observed_at:
                return PositionSaveResult(position=current, status="stale")

        latest = await self.get_latest_for_mmsi(position.mmsi)
        if current is None:
            return PositionSaveResult(position=latest or position, status="inserted")
        return PositionSaveResult(position=latest or position, status="updated_latest")

    async def save_raw(self, position: Position) -> Position:
        """Force-save without staleness check (used for history points)."""
        if position.latitude is not None and position.longitude is not None:
            position.geom = ST_SetSRID(
                ST_MakePoint(position.longitude, position.latitude), 4326
            )
        self._session.add(position)
        await self._session.flush()
        return position

    async def _get_latest_by_identifier(
        self,
        column,
        identifiers: Sequence[str],
    ) -> dict[str, LatestPosition]:
        unique_identifiers = [identifier for identifier in dict.fromkeys(identifiers) if identifier]
        if not unique_identifiers:
            return {}

        ranked = (
            select(
                LatestPosition.mmsi.label("position_mmsi"),
                column.label("identifier"),
                func.row_number()
                .over(partition_by=column, order_by=LatestPosition.observed_at.desc())
                .label("row_number"),
            )
            .where(column.in_(unique_identifiers))
            .subquery()
        )

        result = await self._session.execute(
            select(LatestPosition, ranked.c.identifier)
            .join(ranked, LatestPosition.mmsi == ranked.c.position_mmsi)
            .where(ranked.c.row_number == 1)
        )
        return {
            identifier: position
            for position, identifier in result.all()
            if identifier is not None
        }
