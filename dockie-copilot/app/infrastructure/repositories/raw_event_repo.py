"""
RawEventRepository and SourceHealthRepository.
"""

from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import QuarantinedEvent, RawEvent, SourceHealth


class RawEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, raw_event: RawEvent) -> RawEvent:
        self._session.add(raw_event)
        await self._session.flush()
        return raw_event

    async def save_quarantined(self, event: QuarantinedEvent) -> QuarantinedEvent:
        self._session.add(event)
        await self._session.flush()
        return event


class SourceHealthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all(self) -> Sequence[SourceHealth]:
        result = await self._session.execute(select(SourceHealth))
        return result.scalars().all()

    async def get_by_source(self, source: str) -> Optional[SourceHealth]:
        result = await self._session.execute(
            select(SourceHealth).where(SourceHealth.source == source)
        )
        return result.scalar_one_or_none()

    async def upsert(self, health: SourceHealth) -> SourceHealth:
        """Insert or update source health record."""
        stmt = (
            pg_insert(SourceHealth)
            .values(
                source=health.source,
                source_class=health.source_class,
                automation_safety=health.automation_safety,
                business_safe_default=health.business_safe_default,
                source_status=health.source_status,
                last_success_at=health.last_success_at,
                stale_after_seconds=health.stale_after_seconds,
                degraded_reason=health.degraded_reason,
            )
            .on_conflict_do_update(
                index_elements=["source"],
                set_={
                    "source_status": health.source_status,
                    "last_success_at": health.last_success_at,
                    "degraded_reason": health.degraded_reason,
                    "updated_at": health.updated_at,  # type: ignore[attr-defined]
                },
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()
        return health
