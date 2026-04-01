"""
ShipmentRepository — async SQLAlchemy data access for shipments.
"""

from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.orm import Evidence, Shipment, ShipmentVessel, Vessel


class ShipmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all(self) -> Sequence[Shipment]:
        result = await self._session.execute(
            select(Shipment).options(
                selectinload(Shipment.candidate_vessels).selectinload(ShipmentVessel.vessel),
                selectinload(Shipment.evidence_items),
            )
        )
        return result.scalars().all()

    async def get_all_summary(self) -> Sequence[Shipment]:
        result = await self._session.execute(
            select(Shipment).options(
                selectinload(Shipment.candidate_vessels).selectinload(ShipmentVessel.vessel),
            )
        )
        return result.scalars().all()

    async def get_by_id(self, shipment_id: str) -> Optional[Shipment]:
        result = await self._session.execute(
            select(Shipment)
            .where(Shipment.id == shipment_id)
            .options(
                selectinload(Shipment.candidate_vessels).selectinload(ShipmentVessel.vessel),
                selectinload(Shipment.evidence_items),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_booking_ref(self, booking_ref: str) -> Optional[Shipment]:
        result = await self._session.execute(
            select(Shipment)
            .where(Shipment.booking_ref == booking_ref)
            .options(
                selectinload(Shipment.candidate_vessels).selectinload(ShipmentVessel.vessel),
                selectinload(Shipment.evidence_items),
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, shipment: Shipment) -> Shipment:
        existing = await self.get_by_id(shipment.id)
        if existing:
            # Only update mutable fields
            existing.status = shipment.status
            existing.updated_at = shipment.updated_at  # type: ignore[assignment]
            return existing
        self._session.add(shipment)
        await self._session.flush()
        return shipment

    async def save(self, shipment: Shipment) -> Shipment:
        self._session.add(shipment)
        await self._session.flush()
        return shipment
