"""
Source connector orchestration.

This module lets the system keep fixture data as a stable baseline while
overlaying fresher live data when credentials or public integrations are
available. Connectors are intentionally small and return structured results
that the CLI and API can surface directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.aisstream import capture_positions_for_mmsis, save_capture_snapshot
from app.infrastructure.ingest import ingest_position_snapshot_file, ingest_resource_pack
from app.infrastructure.repositories import SourceHealthRepository
from app.infrastructure.source_feeds import (
    fetch_source_text,
    parse_carrier_schedule_payload,
    parse_port_observation_payload,
    persist_carrier_schedules,
    persist_port_observations,
)
from app.infrastructure.source_policy import get_policy_or_default
from app.models.orm import Shipment, ShipmentVessel, SourceHealth, Vessel

logger = get_logger(__name__)
settings = get_settings()


@dataclass(frozen=True)
class SourceConnectorResult:
    source: str
    attempted: bool
    status: str
    detail: str
    records_ingested: int = 0


@dataclass(frozen=True)
class SourceReadiness:
    source: str
    enabled: bool
    configured: bool
    mode: str
    role: str
    business_safe_default: bool
    detail: str


class SourceConnector(Protocol):
    source_name: str

    def readiness(self) -> SourceReadiness:
        ...

    async def refresh(self, session: AsyncSession) -> SourceConnectorResult:
        ...


class FixtureResourcePackConnector:
    source_name = "fixtures"

    def _refresh_path(self) -> Path:
        refresh_path = Path(settings.resource_pack_refresh_path)
        return refresh_path if refresh_path.exists() else Path(settings.resource_pack_path)

    def readiness(self) -> SourceReadiness:
        path = self._refresh_path()
        enabled = settings.source_fixtures_enabled
        configured = path.exists()
        detail = (
            (
                f"Using {path.name} as the fixture update overlay during refresh."
                if path != Path(settings.resource_pack_path)
                else f"Using {path.name} as the fixture refresh dataset."
            )
            if configured
            else f"Fixture file not found at {path}."
        )
        return SourceReadiness(
            source=self.source_name,
            enabled=enabled,
            configured=configured,
            mode="overlay",
            role="fixture-backed shipment, position, history, and event updates",
            business_safe_default=True,
            detail=detail,
        )

    async def refresh(self, session: AsyncSession) -> SourceConnectorResult:
        readiness = self.readiness()
        if not readiness.enabled:
            return SourceConnectorResult(
                source=self.source_name,
                attempted=False,
                status="disabled",
                detail="Fixture refresh dataset is disabled.",
            )
        if not readiness.configured:
            return SourceConnectorResult(
                source=self.source_name,
                attempted=False,
                status="not_configured",
                detail=readiness.detail,
            )

        counters = await ingest_resource_pack(session, self._refresh_path())
        records_ingested = sum(counters.values())
        return SourceConnectorResult(
            source=self.source_name,
            attempted=True,
            status="healthy",
            detail="Fixture refresh dataset ingested successfully.",
            records_ingested=records_ingested,
        )


class DeferredLiveConnector:
    """
    Connector shell for a live integration that is not fully implemented yet.

    This keeps source readiness visible now, and gives the refresh pipeline a
    stable contract so a real fetcher can replace the placeholder without
    changing callers.
    """

    def __init__(
        self,
        *,
        source_name: str,
        enabled: bool,
        configured: bool,
        role: str,
        detail_if_ready: str,
        detail_if_unconfigured: str,
    ) -> None:
        self.source_name = source_name
        self._enabled = enabled
        self._configured = configured
        self._role = role
        self._detail_if_ready = detail_if_ready
        self._detail_if_unconfigured = detail_if_unconfigured

    def readiness(self) -> SourceReadiness:
        policy = get_policy_or_default(self.source_name)
        return SourceReadiness(
            source=self.source_name,
            enabled=self._enabled,
            configured=self._configured,
            mode="overlay",
            role=self._role,
            business_safe_default=policy.business_safe_default,
            detail=self._detail_if_ready if self._configured else self._detail_if_unconfigured,
        )

    async def refresh(self, session: AsyncSession) -> SourceConnectorResult:
        del session
        readiness = self.readiness()
        if not readiness.enabled:
            return SourceConnectorResult(
                source=self.source_name,
                attempted=False,
                status="disabled",
                detail=f"{self.source_name} overlay refresh is disabled.",
            )
        if not readiness.configured:
            return SourceConnectorResult(
                source=self.source_name,
                attempted=False,
                status="not_configured",
                detail=readiness.detail,
            )

        return SourceConnectorResult(
            source=self.source_name,
            attempted=True,
            status="deferred",
            detail=(
                f"{self.source_name} is configured and ready for live overlay, "
                "but the fetcher is not implemented yet."
            ),
        )


class CarrierScheduleConnector:
    def __init__(self, *, source_name: str, enabled: bool, url: str | None) -> None:
        self.source_name = source_name
        self._enabled = enabled
        self._url = url

    def readiness(self) -> SourceReadiness:
        policy = get_policy_or_default(self.source_name)
        configured = bool(self._url)
        detail = (
            f"Carrier schedule refresh will scrape {self._url}."
            if configured
            else "Set the carrier schedule URL in env to enable live schedule refresh."
        )
        return SourceReadiness(
            source=self.source_name,
            enabled=self._enabled,
            configured=configured,
            mode="overlay",
            role=policy.role,
            business_safe_default=policy.business_safe_default,
            detail=detail,
        )

    async def refresh(self, session: AsyncSession) -> SourceConnectorResult:
        readiness = self.readiness()
        if not readiness.enabled:
            return SourceConnectorResult(
                source=self.source_name,
                attempted=False,
                status="disabled",
                detail=f"{self.source_name} overlay refresh is disabled.",
            )
        if not readiness.configured or not self._url:
            return SourceConnectorResult(
                source=self.source_name,
                attempted=False,
                status="not_configured",
                detail=readiness.detail,
            )
        try:
            payload = await fetch_source_text(self._url)
            schedules = parse_carrier_schedule_payload(payload, carrier=self.source_name, source_url=self._url)
            if not schedules:
                return SourceConnectorResult(
                    source=self.source_name,
                    attempted=True,
                    status="degraded",
                    detail=f"{self.source_name} schedule refresh completed but no usable rows were parsed.",
                )
            counters = await persist_carrier_schedules(session, source_name=self.source_name, schedules=schedules)
            return SourceConnectorResult(
                source=self.source_name,
                attempted=True,
                status="healthy",
                detail=(
                    f"Ingested {counters['schedules']} carrier schedule rows, "
                    f"recorded {counters['revisions']} ETA revisions, and "
                    f"added {counters['evidence']} shipment evidence items."
                ),
                records_ingested=counters["schedules"],
            )
        except Exception as exc:
            logger.warning("carrier_schedule_refresh_failed", source=self.source_name, error=str(exc))
            return SourceConnectorResult(
                source=self.source_name,
                attempted=True,
                status="degraded",
                detail=f"{self.source_name} schedule refresh failed: {exc}",
            )


class NigerianPortsConnector:
    source_name = "nigerian_ports"

    def readiness(self) -> SourceReadiness:
        policy = get_policy_or_default(self.source_name)
        configured = bool(settings.nigerian_ports_url)
        detail = (
            f"Nigerian ports observation refresh will scrape {settings.nigerian_ports_url}."
            if configured
            else "Set NIGERIAN_PORTS_URL to enable berth and anchorage corroboration."
        )
        return SourceReadiness(
            source=self.source_name,
            enabled=settings.source_nigerian_ports_enabled,
            configured=configured,
            mode="overlay",
            role=policy.role,
            business_safe_default=policy.business_safe_default,
            detail=detail,
        )

    async def refresh(self, session: AsyncSession) -> SourceConnectorResult:
        readiness = self.readiness()
        if not readiness.enabled:
            return SourceConnectorResult(
                source=self.source_name,
                attempted=False,
                status="disabled",
                detail="nigerian_ports overlay refresh is disabled.",
            )
        if not readiness.configured or not settings.nigerian_ports_url:
            return SourceConnectorResult(
                source=self.source_name,
                attempted=False,
                status="not_configured",
                detail=readiness.detail,
            )
        try:
            payload = await fetch_source_text(settings.nigerian_ports_url)
            observations = parse_port_observation_payload(payload, source_url=settings.nigerian_ports_url)
            if not observations:
                return SourceConnectorResult(
                    source=self.source_name,
                    attempted=True,
                    status="degraded",
                    detail="Nigerian ports refresh completed but no usable vessel observations were parsed.",
                )
            counters = await persist_port_observations(session, source_name=self.source_name, observations=observations)
            return SourceConnectorResult(
                source=self.source_name,
                attempted=True,
                status="healthy",
                detail=(
                    f"Ingested {counters['observations']} port observations, "
                    f"created {counters['events']} voyage events, and "
                    f"added {counters['evidence']} evidence items."
                ),
                records_ingested=counters["observations"],
            )
        except Exception as exc:
            logger.warning("nigerian_ports_refresh_failed", error=str(exc))
            return SourceConnectorResult(
                source=self.source_name,
                attempted=True,
                status="degraded",
                detail=f"Nigerian ports refresh failed: {exc}",
            )


class AISStreamLiveConnector:
    source_name = "aisstream"

    def readiness(self) -> SourceReadiness:
        configured = bool(settings.aisstream_api_key)
        policy = get_policy_or_default(self.source_name)
        detail = (
            "AISStream credentials present. Refresh will capture a bounded live position snapshot."
            if configured
            else "Provide AISSTREAM_API_KEY to enable live vessel positions."
        )
        return SourceReadiness(
            source=self.source_name,
            enabled=settings.source_aisstream_enabled,
            configured=configured,
            mode="overlay",
            role="live vessel movement overlay",
            business_safe_default=policy.business_safe_default,
            detail=detail,
        )

    async def refresh(self, session: AsyncSession) -> SourceConnectorResult:
        readiness = self.readiness()
        if not readiness.enabled:
            return SourceConnectorResult(
                source=self.source_name,
                attempted=False,
                status="disabled",
                detail="aisstream overlay refresh is disabled.",
            )
        if not readiness.configured or not settings.aisstream_api_key:
            return SourceConnectorResult(
                source=self.source_name,
                attempted=False,
                status="not_configured",
                detail=readiness.detail,
            )

        tracked_mmsis = await _load_tracked_mmsis(session)
        if not tracked_mmsis:
            return SourceConnectorResult(
                source=self.source_name,
                attempted=False,
                status="idle",
                detail="No shipment-linked MMSIs are available for AISStream capture yet.",
            )

        try:
            capture = await capture_positions_for_mmsis(
                api_key=settings.aisstream_api_key,
                mmsis=tracked_mmsis,
            )
        except Exception as exc:
            logger.warning("aisstream_capture_failed", error=str(exc))
            return SourceConnectorResult(
                source=self.source_name,
                attempted=True,
                status="degraded",
                detail=f"AISStream targeted capture failed: {exc}",
            )

        snapshot_path = save_capture_snapshot(settings.aisstream_capture_snapshot_path, capture)

        if not capture.positions:
            return SourceConnectorResult(
                source=self.source_name,
                attempted=True,
                status="degraded",
                detail=(
                    "AISStream capture completed but returned no matching live positions "
                    f"for {capture.requested_mmsis} tracked MMSIs after inspecting "
                    f"{capture.inspected_messages} messages. Snapshot saved to {snapshot_path}."
                ),
            )

        counters = await ingest_position_snapshot_file(session, snapshot_path, commit=False)
        detail = (
            f"Captured {capture.matched_positions} live AIS positions for "
            f"{capture.requested_mmsis} tracked MMSIs after inspecting "
            f"{capture.inspected_messages} messages. Snapshot saved to {snapshot_path}."
        )
        if capture.error:
            detail += f" Stream ended early: {capture.error}."
        return SourceConnectorResult(
            source=self.source_name,
            attempted=True,
            status="healthy",
            detail=detail,
            records_ingested=counters["positions"],
        )


def build_source_connectors() -> list[SourceConnector]:
    return [
        FixtureResourcePackConnector(),
        AISStreamLiveConnector(),
        CarrierScheduleConnector(
            source_name="sallaum",
            enabled=settings.source_sallaum_enabled,
            url=settings.sallaum_schedule_url,
        ),
        CarrierScheduleConnector(
            source_name="grimaldi",
            enabled=settings.source_grimaldi_enabled,
            url=settings.grimaldi_schedule_url,
        ),
        NigerianPortsConnector(),
        DeferredLiveConnector(
            source_name="historical_ais",
            enabled=settings.source_historical_ais_enabled,
            configured=True,
            role="historical track enrichment overlay",
            detail_if_ready="Historical AIS backfill can be loaded from fixtures or a provider adapter.",
            detail_if_unconfigured="Historical AIS backfill can be loaded from fixtures or a provider adapter.",
        ),
        DeferredLiveConnector(
            source_name="official_sanctions",
            enabled=settings.source_official_sanctions_enabled,
            configured=True,
            role="compliance enrichment overlay",
            detail_if_ready="Official sanctions ingest can be wired in without changing refresh callers.",
            detail_if_unconfigured="Official sanctions ingest can be wired in without changing refresh callers.",
        ),
    ]


async def refresh_sources(session: AsyncSession) -> list[SourceConnectorResult]:
    results: list[SourceConnectorResult] = []
    for connector in build_source_connectors():
        result = await connector.refresh(session)
        results.append(result)
        await _update_source_health_from_result(session, result)
    return results


def list_source_readiness() -> list[SourceReadiness]:
    return [connector.readiness() for connector in build_source_connectors()]


async def _update_source_health_from_result(
    session: AsyncSession,
    result: SourceConnectorResult,
) -> None:
    if result.source == "fixtures":
        return

    repo = SourceHealthRepository(session)
    policy = get_policy_or_default(result.source)
    existing = await repo.get_by_source(result.source)

    status_map = {
        "healthy": "healthy",
        "deferred": "manual",
        "disabled": "manual",
        "not_configured": "manual",
        "idle": "manual",
    }
    source_status = status_map.get(result.status, "degraded")

    record = existing or SourceHealth(
        source=result.source,
        source_class=policy.source_class,
        automation_safety=policy.automation_safety,
        business_safe_default=policy.business_safe_default,
        stale_after_seconds=policy.stale_after_seconds,
        source_status=source_status,
    )
    record.source_status = source_status
    if result.status == "healthy":
        from datetime import datetime, timezone
        record.last_success_at = datetime.now(timezone.utc)
    record.degraded_reason = None if result.status == "healthy" else result.detail
    await repo.upsert(record)


async def _load_tracked_mmsis(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(Vessel.mmsi)
        .join(ShipmentVessel, ShipmentVessel.vessel_id == Vessel.id)
        .join(Shipment, Shipment.id == ShipmentVessel.shipment_id)
        .where(Vessel.mmsi.is_not(None))
    )
    return [str(mmsi) for mmsi in result.scalars().all() if mmsi]
