"""
VesselRepository — async SQLAlchemy data access for vessels.
"""

from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Vessel


class VesselRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_imo(self, imo: str) -> Optional[Vessel]:
        result = await self._session.execute(
            select(Vessel).where(Vessel.imo == imo)
        )
        return result.scalar_one_or_none()

    async def get_by_mmsi(self, mmsi: str) -> Optional[Vessel]:
        result = await self._session.execute(
            select(Vessel).where(Vessel.mmsi == mmsi)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Vessel]:
        result = await self._session.execute(
            select(Vessel).where(Vessel.name == name)
        )
        return result.scalars().first()

    async def get_all(self) -> Sequence[Vessel]:
        result = await self._session.execute(select(Vessel))
        return result.scalars().all()

    async def save(self, vessel: Vessel) -> Vessel:
        self._session.add(vessel)
        await self._session.flush()
        return vessel

    async def get_or_create(self, imo: Optional[str], mmsi: Optional[str], name: str) -> Vessel:
        """Find by IMO or MMSI, create if not found."""
        if imo:
            existing = await self.get_by_imo(imo)
            if existing:
                return existing
        if mmsi:
            existing = await self.get_by_mmsi(mmsi)
            if existing:
                return existing
        existing = await self.get_by_name(name)
        if existing:
            return existing

        vessel = Vessel(imo=imo, mmsi=mmsi, name=name)
        return await self.save(vessel)
