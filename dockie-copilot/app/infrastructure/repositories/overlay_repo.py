"""
Repositories for carrier schedules, ETA revisions, and port observations.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import CarrierSchedule, ETARevisionLog, PortObservation


class CarrierScheduleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, row: CarrierSchedule) -> CarrierSchedule:
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_for_shipment(
        self,
        *,
        carrier: str,
        vessel_imo: str | None = None,
        vessel_name: str | None = None,
        port_locode: str | None = None,
        limit: int = 10,
    ) -> Sequence[CarrierSchedule]:
        stmt = (
            select(CarrierSchedule)
            .where(CarrierSchedule.carrier == carrier)
            .order_by(CarrierSchedule.scraped_at.desc())
            .limit(limit)
        )
        if vessel_imo:
            stmt = stmt.where(CarrierSchedule.vessel_imo == vessel_imo)
        elif vessel_name:
            stmt = stmt.where(CarrierSchedule.vessel_name == vessel_name)
        if port_locode:
            stmt = stmt.where(CarrierSchedule.port_locode == port_locode)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_latest_snapshot(
        self,
        *,
        carrier: str,
        limit: int = 100,
    ) -> Sequence[CarrierSchedule]:
        latest_scraped_at = await self._session.scalar(
            select(func.max(CarrierSchedule.scraped_at)).where(CarrierSchedule.carrier == carrier)
        )
        if latest_scraped_at is None:
            return []

        result = await self._session.execute(
            select(CarrierSchedule)
            .where(CarrierSchedule.carrier == carrier)
            .where(CarrierSchedule.scraped_at == latest_scraped_at)
            .order_by(CarrierSchedule.eta.asc().nulls_last(), CarrierSchedule.vessel_name.asc())
            .limit(limit)
        )
        return result.scalars().all()


class ETARevisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, row: ETARevisionLog) -> ETARevisionLog:
        self._session.add(row)
        await self._session.flush()
        return row

    async def latest_for_shipment(self, shipment_id: str) -> ETARevisionLog | None:
        result = await self._session.execute(
            select(ETARevisionLog)
            .where(ETARevisionLog.shipment_id == shipment_id)
            .order_by(ETARevisionLog.revision_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_shipment(self, shipment_id: str, limit: int = 20) -> Sequence[ETARevisionLog]:
        result = await self._session.execute(
            select(ETARevisionLog)
            .where(ETARevisionLog.shipment_id == shipment_id)
            .order_by(ETARevisionLog.revision_at.desc())
            .limit(limit)
        )
        return result.scalars().all()


class PortObservationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, row: PortObservation) -> PortObservation:
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_for_shipment(
        self,
        *,
        vessel_imo: str | None = None,
        vessel_mmsi: str | None = None,
        vessel_name: str | None = None,
        port_locode: str | None = None,
        limit: int = 20,
    ) -> Sequence[PortObservation]:
        stmt = select(PortObservation).order_by(PortObservation.observed_at.desc()).limit(limit)
        if vessel_imo:
            stmt = stmt.where(PortObservation.vessel_imo == vessel_imo)
        elif vessel_mmsi:
            stmt = stmt.where(PortObservation.vessel_mmsi == vessel_mmsi)
        elif vessel_name:
            stmt = stmt.where(PortObservation.vessel_name == vessel_name)
        if port_locode:
            stmt = stmt.where(PortObservation.port_locode == port_locode)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def exists_recent_observation(
        self,
        *,
        port_locode: str,
        observed_at: datetime,
        vessel_name: str | None,
        status: str | None,
    ) -> bool:
        result = await self._session.execute(
            select(PortObservation.id)
            .where(PortObservation.port_locode == port_locode)
            .where(PortObservation.observed_at == observed_at)
            .where(PortObservation.vessel_name == vessel_name)
            .where(PortObservation.status == status)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
