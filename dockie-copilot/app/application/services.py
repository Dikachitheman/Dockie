"""
Application services — orchestrate repositories and domain logic.

No direct DB access; no HTTP calls.
Returns Pydantic schemas ready for API consumption and agent tools.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from hashlib import sha1
import re
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import sanitize_text
from app.domain import logic as domain_logic
from app.domain.models import ETAConfidence, FreshnessLevel, Position as DomainPosition
from app.infrastructure.cache import (
    CacheBackend,
    CacheCoordinator,
    build_cache_coordinator,
    get_cache_backend,
    invalidate_cache_prefix,
    invalidate_shipment_cache,
)
from app.infrastructure.database import AsyncSessionFactory
from app.infrastructure.normalizer import _parse_datetime
from app.infrastructure.embeddings import embedding_service
from app.infrastructure.repositories import (
    CarrierScheduleRepository,
    ETARevisionRepository,
    PositionRepository,
    PortObservationRepository,
    ShipmentRepository,
    SourceHealthRepository,
    VesselRepository,
)
from app.infrastructure.source_policy import get_policy_or_default
from app.infrastructure.sources import list_source_readiness
from app.models.orm import (
    CarrierPerformanceMetric,
    ClearanceChecklist,
    DemurrageTariff,
    DocumentChunk,
    Evidence,
    FXRate,
    LatestPosition,
    PortCongestionReading,
    PortCongestionSeasonality,
    Shipment,
    ShipmentVessel,
    Vessel,
    VoyageEvent,
)
from app.schemas.requests import ManualShipmentCreateRequest
from app.schemas.responses import (
    AppBootstrapSchema,
    AgentOutputSchema,
    CarrierPerformanceSchema,
    CandidateVesselSchema,
    ClearanceChecklistSchema,
    DemurrageExposureSchema,
    ETAConfidenceSchema,
    ETARevisionSchema,
    EvidenceSchema,
    KnowledgeSearchResponseSchema,
    KnowledgeSnippetSchema,
    PortCongestionPointSchema,
    PortCongestionSummarySchema,
    PortObservationSchema,
    PositionSchema,
    RealisticETASchema,
    ShipmentBundleSchema,
    ShipmentDetailSchema,
    ShipmentComparisonItemSchema,
    ShipmentComparisonSchema,
    ShipmentHistorySchema,
    ShipmentStatusSchema,
    ShipmentSummarySchema,
    StandbyAgentSchema,
    SourceHealthSchema,
    SourceReadinessSchema,
    TrackPointSchema,
    UserNotificationSchema,
    VesselAnomalySchema,
    VesselSwapSchema,
    VoyageEventSchema,
)
from sqlalchemy import select

logger = get_logger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# ShipmentService
# ---------------------------------------------------------------------------

class ShipmentService:
    def __init__(
        self,
        session: AsyncSession,
        cache: CacheBackend | None = None,
        cache_coordinator: CacheCoordinator | None = None,
    ) -> None:
        self._session = session
        self._cache = cache or get_cache_backend()
        self._cache_coordinator = cache_coordinator or build_cache_coordinator(self._cache)
        self._shipment_repo = ShipmentRepository(session)
        self._vessel_repo = VesselRepository(session)
        self._position_repo = PositionRepository(session)
        self._schedule_repo = CarrierScheduleRepository(session)
        self._revision_repo = ETARevisionRepository(session)
        self._port_obs_repo = PortObservationRepository(session)

    async def list_shipments(self) -> list[ShipmentSummarySchema]:
        cache_key = "shipments:list"
        cached = await self._cache.get_json(cache_key)
        if cached is not None:
            logger.info("cache_hit", key=cache_key)
            return [ShipmentSummarySchema.model_validate(item) for item in cached]

        shipments = await self._shipment_repo.get_all_summary()
        result = [self._to_shipment_summary_schema(shipment) for shipment in shipments]
        await self._cache.set_json(
            cache_key,
            [item.model_dump(mode="json") for item in result],
            settings.cache_list_shipments_ttl_seconds,
        )
        logger.info("cache_miss", key=cache_key)
        return result

    async def get_shipment_detail(self, shipment_id: str) -> Optional[ShipmentDetailSchema]:
        shipment = await self._shipment_repo.get_by_id(shipment_id)
        if not shipment:
            return None
        return self._to_shipment_detail_schema(shipment)

    async def get_shipment_bundle(self, shipment_id: str) -> Optional[ShipmentBundleSchema]:
        shipment = await self._shipment_repo.get_by_id(shipment_id)
        if not shipment:
            return None

        detail = self._to_shipment_detail_schema(shipment)
        status = await self._get_or_build_shipment_status(
            f"shipments:status:{shipment_id}",
            shipment_id,
            shipment=shipment,
        )
        history = await self._get_or_build_shipment_history(
            f"shipments:history:{shipment_id}",
            shipment_id,
            shipment=shipment,
        )
        if status is None or history is None:
            return None
        return ShipmentBundleSchema(detail=detail, status=status, history=history)

    async def create_manual_shipment(
        self,
        payload: ManualShipmentCreateRequest,
    ) -> ShipmentDetailSchema:
        vessel_name = sanitize_text(payload.vessel_name)
        mmsi = sanitize_text(payload.mmsi)
        imo = sanitize_text(payload.imo) if payload.imo else None
        label = sanitize_text(payload.shipment_label)
        carrier = sanitize_text(payload.carrier)

        shipment = Shipment(
            id=f"manual-{uuid.uuid4().hex[:8]}",
            booking_ref=self._build_manual_booking_ref(label, mmsi),
            carrier=carrier,
            service_lane=sanitize_text(payload.service_lane) if payload.service_lane else None,
            load_port=sanitize_text(payload.load_port) if payload.load_port else None,
            discharge_port=sanitize_text(payload.discharge_port) if payload.discharge_port else None,
            cargo_type=sanitize_text(payload.cargo_type) if payload.cargo_type else None,
            units=payload.units,
            status="open",
            declared_departure_date=_parse_datetime(payload.declared_departure_date),
            declared_eta_date=_parse_datetime(payload.declared_eta_date),
        )
        await self._shipment_repo.save(shipment)

        vessel = await self._vessel_repo.get_or_create(imo, mmsi, vessel_name)
        self._session.add(
            ShipmentVessel(
                shipment_id=shipment.id,
                vessel_id=vessel.id,
                is_primary=True,
            )
        )
        self._session.add(
            Evidence(
                shipment_id=shipment.id,
                source="manual_tracking",
                captured_at=datetime.now(timezone.utc),
                claim=(
                    f"Manual live tracking added for vessel {vessel_name} "
                    f"(MMSI {mmsi}{f', IMO {imo}' if imo else ''})."
                ),
            )
        )
        await self._session.commit()

        await invalidate_cache_prefix("shipments:list")
        await invalidate_shipment_cache(shipment.id)

        created = await self.get_shipment_detail(shipment.id)
        if created is None:
            raise RuntimeError(f"Created shipment {shipment.id} could not be reloaded.")
        return created

    async def get_shipment_status(self, shipment_id: str) -> Optional[ShipmentStatusSchema]:
        cache_key = f"shipments:status:{shipment_id}"
        cached = await self._cache.get_json(cache_key)
        if cached is not None:
            logger.info("cache_hit", key=cache_key)
            return ShipmentStatusSchema.model_validate(cached)
        return await self._get_or_build_shipment_status(cache_key, shipment_id)

    async def get_shipment_history(self, shipment_id: str) -> Optional[ShipmentHistorySchema]:
        cache_key = f"shipments:history:{shipment_id}"
        cached = await self._cache.get_json(cache_key)
        if cached is not None:
            logger.info("cache_hit", key=cache_key)
            return ShipmentHistorySchema.model_validate(cached)
        return await self._get_or_build_shipment_history(cache_key, shipment_id)

    async def get_eta_revisions(self, shipment_id: str) -> list[ETARevisionSchema]:
        revisions = await self._revision_repo.list_for_shipment(shipment_id)
        return [ETARevisionSchema.model_validate(item) for item in revisions]

    async def get_port_observations(self, shipment_id: str) -> list[PortObservationSchema]:
        shipment = await self._shipment_repo.get_by_id(shipment_id)
        if not shipment:
            return []

        matched: list[PortObservationSchema] = []
        seen_ids: set[tuple[str, datetime]] = set()
        for sv in shipment.candidate_vessels:
            vessel = sv.vessel
            rows = await self._port_obs_repo.list_for_shipment(
                vessel_imo=vessel.imo,
                vessel_mmsi=vessel.mmsi,
                vessel_name=vessel.name,
                port_locode=shipment.discharge_port,
            )
            for row in rows:
                marker = (row.port_locode, row.observed_at)
                if marker in seen_ids:
                    continue
                seen_ids.add(marker)
                matched.append(PortObservationSchema.model_validate(row))
        return matched

    async def get_clearance_checklist(self, shipment_id: str) -> ClearanceChecklistSchema | None:
        shipment = await self._shipment_repo.get_by_id(shipment_id)
        if not shipment:
            return None

        row = await self._session.get(ClearanceChecklist, shipment_id)
        return self._build_clearance_checklist_schema(shipment_id, row)

    async def get_realistic_eta(self, shipment_id: str) -> RealisticETASchema | None:
        shipment = await self._shipment_repo.get_by_id(shipment_id)
        if not shipment:
            return None

        latest_pos = await self._get_latest_candidate_position(shipment)
        checklist = await self._session.get(ClearanceChecklist, shipment_id)
        now = datetime.now(timezone.utc)
        declared_eta = shipment.declared_eta_date
        relevant_month = (declared_eta or now).month

        congestion_reading = await self._session.scalar(
            select(PortCongestionReading)
            .where(PortCongestionReading.port_locode == shipment.discharge_port)
            .order_by(PortCongestionReading.observed_at.desc())
            .limit(1)
        )
        seasonality = await self._session.scalar(
            select(PortCongestionSeasonality)
            .where(PortCongestionSeasonality.port_locode == shipment.discharge_port)
            .where(PortCongestionSeasonality.month == relevant_month)
            .limit(1)
        )

        congestion_days = max(
            congestion_reading.delay_days if congestion_reading else 0.0,
            seasonality.median_wait_days if seasonality else 0.0,
        )

        if latest_pos and latest_pos.navigation_status == "at_anchor":
            estimated_anchor_arrival = latest_pos.observed_at
        elif latest_pos:
            estimated_anchor_arrival = latest_pos.observed_at.replace(minute=0, second=0, microsecond=0)
        else:
            estimated_anchor_arrival = declared_eta

        if estimated_anchor_arrival is None:
            estimated_anchor_arrival = now

        berth_start = estimated_anchor_arrival
        berth_end = estimated_anchor_arrival
        if congestion_days > 0:
            from datetime import timedelta

            berth_start = estimated_anchor_arrival + timedelta(days=max(congestion_days - 1.0, 0.0))
            berth_end = estimated_anchor_arrival + timedelta(days=max(seasonality.p75_wait_days if seasonality and seasonality.p75_wait_days else congestion_days + 1.0, congestion_days))

        checklist_schema = self._build_clearance_checklist_schema(shipment_id, checklist)
        clearance_risk_days = max(0, len(checklist_schema.missing_items) - 1)
        from datetime import timedelta

        release_start = berth_start + timedelta(days=max(1, clearance_risk_days))
        release_end = berth_end + timedelta(days=max(2, clearance_risk_days + 1))

        supporting_factors: list[str] = []
        if congestion_reading:
            supporting_factors.append(
                f"Latest congestion reading at {shipment.discharge_port}: {congestion_reading.delay_days:.1f} delay days."
            )
        if seasonality:
            supporting_factors.append(
                f"Seasonal berth median for month {relevant_month}: {seasonality.median_wait_days:.1f} days."
            )
        if checklist_schema.missing_items:
            supporting_factors.append(
                f"Clearance is incomplete: {', '.join(checklist_schema.missing_items)}."
            )
        if latest_pos and latest_pos.navigation_status == "at_anchor":
            supporting_factors.append("Vessel is already at anchor, so berth timing depends mainly on congestion.")

        congestion_level = "low"
        if congestion_days >= 5:
            congestion_level = "high"
        elif congestion_days >= 2:
            congestion_level = "medium"

        confidence_note = "Built from declared ETA, latest vessel state, simulated congestion, and checklist readiness."
        if latest_pos is None:
            confidence_note = "No live position available. Estimate leans on declared ETA and simulated congestion."

        return RealisticETASchema(
            shipment_id=shipment_id,
            declared_eta=declared_eta,
            latest_position_source=latest_pos.source if latest_pos else None,
            latest_position_observed_at=latest_pos.observed_at if latest_pos else None,
            estimated_anchor_arrival=estimated_anchor_arrival,
            realistic_berth_window_start=berth_start,
            realistic_berth_window_end=berth_end,
            realistic_release_window_start=release_start,
            realistic_release_window_end=release_end,
            congestion_level=congestion_level,
            confidence_note=confidence_note,
            supporting_factors=supporting_factors,
        )

    async def get_demurrage_exposure(self, shipment_id: str) -> DemurrageExposureSchema | None:
        shipment = await self._shipment_repo.get_by_id(shipment_id)
        if not shipment:
            return None

        checklist = await self._session.get(ClearanceChecklist, shipment_id)
        realistic = await self.get_realistic_eta(shipment_id)
        if realistic is None:
            return None

        vehicle_type = "equipment" if (shipment.cargo_type or "").lower().find("equipment") >= 0 else "default"
        tariff = await self._session.scalar(
            select(DemurrageTariff)
            .where(DemurrageTariff.terminal_locode == shipment.discharge_port)
            .where(DemurrageTariff.vehicle_type == vehicle_type)
            .order_by(DemurrageTariff.effective_from.desc())
            .limit(1)
        )
        if tariff is None:
            tariff = await self._session.scalar(
                select(DemurrageTariff)
                .where(DemurrageTariff.terminal_locode == shipment.discharge_port)
                .where(DemurrageTariff.vehicle_type == "default")
                .order_by(DemurrageTariff.effective_from.desc())
                .limit(1)
            )

        fx = await self._session.scalar(
            select(FXRate)
            .where(FXRate.currency_pair == "USD/NGN")
            .order_by(FXRate.observed_at.desc())
            .limit(1)
        )
        checklist_schema = self._build_clearance_checklist_schema(shipment_id, checklist)
        clearance_risk_days = max(0, len(checklist_schema.missing_items) - 1)

        free_days = tariff.free_days if tariff else 5
        daily_rate_ngn = tariff.daily_rate_ngn if tariff and tariff.daily_rate_ngn is not None else 45000.0
        daily_rate_usd = tariff.daily_rate_usd if tariff else None
        units = shipment.units or 1
        projected_days = max(1, clearance_risk_days + (2 if realistic.congestion_level == "high" else 1 if realistic.congestion_level == "medium" else 0))
        projected_cost_ngn = float(projected_days * units * daily_rate_ngn)
        projected_cost_usd = float(projected_cost_ngn / fx.rate) if fx and fx.rate else daily_rate_usd

        from datetime import timedelta

        free_days_end = (
            realistic.realistic_berth_window_start + timedelta(days=free_days)
            if realistic.realistic_berth_window_start
            else None
        )
        risk_level = "low"
        if projected_cost_ngn >= 2_000_000:
            risk_level = "high"
        elif projected_cost_ngn >= 750_000:
            risk_level = "medium"

        notes = [
            f"Projected using {units} unit(s), {projected_days} risk day(s), and terminal {shipment.discharge_port}.",
        ]
        if checklist_schema.missing_items:
            notes.append(f"Missing checklist items: {', '.join(checklist_schema.missing_items)}.")
        if realistic.congestion_level != "low":
            notes.append(f"Congestion level is {realistic.congestion_level}.")

        return DemurrageExposureSchema(
            shipment_id=shipment_id,
            terminal_locode=shipment.discharge_port,
            free_days=free_days,
            daily_rate_ngn=float(daily_rate_ngn),
            daily_rate_usd=float(daily_rate_usd) if daily_rate_usd is not None else None,
            projected_cost_ngn=projected_cost_ngn,
            projected_cost_usd=projected_cost_usd,
            clearance_risk_days=clearance_risk_days,
            risk_level=risk_level,
            free_days_end=free_days_end,
            notes=notes,
        )

    async def get_port_congestion_summary(self, shipment_id: str) -> PortCongestionSummarySchema | None:
        shipment = await self._shipment_repo.get_by_id(shipment_id)
        if not shipment or not shipment.discharge_port:
            return None

        rows = (
            await self._session.execute(
                select(PortCongestionReading)
                .where(PortCongestionReading.port_locode == shipment.discharge_port)
                .order_by(PortCongestionReading.observed_at.desc())
                .limit(7)
            )
        ).scalars().all()
        seasonality = await self._session.scalar(
            select(PortCongestionSeasonality)
            .where(PortCongestionSeasonality.port_locode == shipment.discharge_port)
            .where(PortCongestionSeasonality.month == datetime.now(timezone.utc).month)
            .limit(1)
        )

        current_wait = rows[0].delay_days if rows else 0.0
        p75_wait = seasonality.p75_wait_days if seasonality else None
        p90_wait = seasonality.p90_wait_days if seasonality else None
        seasonal_median = seasonality.median_wait_days if seasonality else None
        above_seasonal = round(current_wait - seasonal_median, 1) if seasonal_median is not None else None

        return PortCongestionSummarySchema(
            shipment_id=shipment_id,
            port_locode=shipment.discharge_port,
            current_wait_days=current_wait,
            p75_wait_days=p75_wait,
            p90_wait_days=p90_wait,
            seasonal_median_days=seasonal_median,
            above_seasonal_days=above_seasonal,
            recent_readings=[
                PortCongestionPointSchema(
                    observed_at=row.observed_at,
                    delay_days=row.delay_days,
                    queue_vessels=row.queue_vessels,
                    source=row.source,
                )
                for row in reversed(rows)
            ],
        )

    async def list_carrier_performance(self, service_lane: str | None = None) -> list[CarrierPerformanceSchema]:
        stmt = select(CarrierPerformanceMetric).order_by(
            CarrierPerformanceMetric.year_month.desc(),
            CarrierPerformanceMetric.on_time_rate.desc().nullslast(),
        )
        if service_lane:
            stmt = stmt.where(CarrierPerformanceMetric.service_lane == service_lane)

        rows = (await self._session.execute(stmt)).scalars().all()
        latest_by_carrier: dict[str, CarrierPerformanceMetric] = {}
        for row in rows:
            if row.carrier not in latest_by_carrier:
                latest_by_carrier[row.carrier] = row

        return [
            CarrierPerformanceSchema(
                carrier=row.carrier,
                service_lane=row.service_lane,
                year_month=row.year_month,
                median_delay_days=row.median_delay_days,
                on_time_rate=row.on_time_rate,
                sample_count=row.sample_count,
                notes=row.notes,
            )
            for row in latest_by_carrier.values()
        ]

    async def compare_shipments(self, shipment_ids: list[str] | None = None) -> ShipmentComparisonSchema:
        shipments = list(await self._shipment_repo.get_all())
        if shipment_ids:
            shipment_ids_set = set(shipment_ids)
            shipments = [shipment for shipment in shipments if shipment.id in shipment_ids_set]
        else:
            shipments = [shipment for shipment in shipments if shipment.status != "delivered"]

        items: list[ShipmentComparisonItemSchema] = []
        for shipment in shipments:
            status = await self.get_shipment_status(shipment.id)
            if status is None:
                continue
            risk_score = 0.0
            if status.status == "delayed":
                risk_score += 3.0
            if status.eta_confidence.freshness == "stale":
                risk_score += 2.5
            elif status.eta_confidence.freshness == "unknown":
                risk_score += 1.5
            if len(status.candidate_vessels) > 1:
                risk_score += 1.5
            if status.freshness_warning:
                risk_score += 1.0
            summary = f"{status.status.replace('_', ' ')}; ETA freshness is {status.eta_confidence.freshness}."
            items.append(
                ShipmentComparisonItemSchema(
                    shipment_id=shipment.id,
                    booking_ref=shipment.booking_ref,
                    carrier=shipment.carrier,
                    status=shipment.status,
                    risk_score=round(risk_score, 2),
                    summary=summary,
                    freshness=status.eta_confidence.freshness,
                )
            )

        items.sort(key=lambda item: item.risk_score, reverse=True)
        recommendation = (
            f"{items[0].shipment_id} needs attention first because it carries the highest simulated operational risk."
            if items
            else None
        )
        return ShipmentComparisonSchema(
            compared_at=datetime.now(timezone.utc),
            shipments=items,
            recommendation=recommendation,
        )

    async def detect_vessel_anomaly(self, shipment_id: str) -> VesselAnomalySchema | None:
        shipment = await self._shipment_repo.get_by_id(shipment_id)
        if not shipment:
            return None
        status = await self.get_shipment_status(shipment_id)
        history = await self.get_shipment_history(shipment_id)
        if status is None or history is None:
            return None

        indicators: list[str] = []
        latest = status.latest_position
        if status.eta_confidence.freshness == "stale":
            indicators.append("Position data is stale.")
        if latest and latest.navigation_status == "at_anchor":
            indicators.append("Vessel is at anchor close to the discharge corridor.")
        if latest and latest.sog_knots is not None and latest.sog_knots < 1:
            indicators.append("Speed is near zero.")
        if shipment.declared_eta_date and shipment.declared_eta_date < datetime.now(timezone.utc):
            indicators.append("Declared ETA has already passed.")
        if len(history.track) >= 2:
            last_two = history.track[-2:]
            speeds = [point.sog_knots or 0 for point in last_two]
            if abs(speeds[-1] - speeds[0]) > 5:
                indicators.append("Recent speed changed sharply across the last two observations.")

        severity = "none"
        if len(indicators) >= 3:
            severity = "high"
        elif len(indicators) == 2:
            severity = "medium"
        elif len(indicators) == 1:
            severity = "low"

        summary = "No clear simulated anomaly detected."
        if indicators:
            summary = " ".join(indicators)

        return VesselAnomalySchema(
            shipment_id=shipment_id,
            severity=severity,
            summary=summary,
            indicators=indicators,
            recommended_action="Review berth timing and readiness if the anomaly persists." if indicators else None,
        )

    async def check_vessel_swap(self, shipment_id: str) -> VesselSwapSchema | None:
        shipment = await self._shipment_repo.get_by_id(shipment_id)
        if not shipment:
            return None

        candidates = shipment.candidate_vessels
        if len(candidates) < 2:
            primary_name = candidates[0].vessel.name if candidates else None
            return VesselSwapSchema(
                shipment_id=shipment_id,
                confidence=0.0,
                hypothesis="No vessel swap signal because this shipment has only one candidate vessel.",
                primary_vessel=primary_name,
            )

        primary = candidates[0].vessel
        secondary = candidates[1].vessel
        primary_pos = await self._position_repo.get_latest_for_mmsi(primary.mmsi or "")
        secondary_pos = await self._position_repo.get_latest_for_mmsi(secondary.mmsi or "")

        confidence = 0.1
        signals: list[str] = []
        if primary_pos is None:
            confidence += 0.2
            signals.append("Primary candidate has no recent live position.")
        if secondary_pos and secondary_pos.destination_text and shipment.discharge_port and secondary_pos.destination_text.lower().find("tin") >= 0:
            confidence += 0.25
            signals.append("Secondary candidate destination text aligns with the Lagos discharge pattern.")
        if secondary_pos and secondary_pos.sog_knots and secondary_pos.sog_knots > 10:
            confidence += 0.2
            signals.append("Secondary candidate is making active corridor progress.")
        if primary_pos and primary_pos.sog_knots is not None and primary_pos.sog_knots < 5:
            confidence += 0.2
            signals.append("Primary candidate is moving too slowly to inspire confidence.")
        confidence = min(confidence, 0.95)

        hypothesis = "Primary candidate still looks more likely."
        if confidence >= 0.5:
            hypothesis = f"Secondary candidate {secondary.name} may now be the more plausible carrying vessel."

        return VesselSwapSchema(
            shipment_id=shipment_id,
            confidence=round(confidence, 2),
            hypothesis=hypothesis,
            primary_vessel=primary.name,
            secondary_vessel=secondary.name,
            supporting_signals=signals,
            recommended_action="Draft a carrier inquiry and confirm the active hull for this booking." if confidence >= 0.5 else None,
        )

    async def import_live_carrier_shipments(
        self,
        *,
        carriers: list[str] | None = None,
        per_carrier_limit: int = 5,
    ) -> list[ShipmentDetailSchema]:
        selected_carriers = carriers or ["sallaum", "grimaldi"]
        created_or_updated: list[ShipmentDetailSchema] = []

        for carrier in selected_carriers:
            rows = await self._schedule_repo.list_latest_snapshot(
                carrier=carrier,
                limit=max(per_carrier_limit * 4, per_carrier_limit),
            )
            selected_rows = self._select_live_import_rows(rows, limit=per_carrier_limit)
            logger.info(
                "carrier_live_import_candidates",
                carrier=carrier,
                snapshot_rows=len(rows),
                selected_rows=len(selected_rows),
                vessels=[row.vessel_name for row in selected_rows],
            )
            for row in selected_rows:
                shipment = await self._upsert_live_carrier_shipment(row)
                detail = await self.get_shipment_detail(shipment.id)
                if detail is not None:
                    created_or_updated.append(detail)

        await self._session.commit()
        await invalidate_cache_prefix("shipments:list")
        for detail in created_or_updated:
            await invalidate_shipment_cache(detail.id)
        return created_or_updated

    async def _get_or_build_shipment_status(
        self,
        cache_key: str,
        shipment_id: str,
        shipment: Shipment | None = None,
    ) -> Optional[ShipmentStatusSchema]:
        lock_key = f"lock:{cache_key}"
        lease = await self._cache_coordinator.try_acquire(
            lock_key,
            lease_seconds=settings.cache_singleflight_lock_ttl_seconds,
        )

        if not lease.acquired:
            cached = await self._cache_coordinator.wait_for_json(
                cache_key,
                timeout_ms=settings.cache_singleflight_wait_timeout_ms,
                poll_interval_ms=settings.cache_singleflight_poll_interval_ms,
            )
            if cached is not None:
                logger.info("cache_fill_shared", key=cache_key)
                return ShipmentStatusSchema.model_validate(cached)

        if lease.acquired:
            try:
                cached = await self._cache.get_json(cache_key)
                if cached is not None:
                    logger.info("cache_hit_after_lock", key=cache_key)
                    return ShipmentStatusSchema.model_validate(cached)

                return await self._build_and_cache_shipment_status(cache_key, shipment_id, shipment=shipment)
            finally:
                await self._cache_coordinator.release(lease)

        logger.info("cache_fill_wait_timeout", key=cache_key)
        return await self._build_and_cache_shipment_status(cache_key, shipment_id, shipment=shipment)

    async def _build_and_cache_shipment_status(
        self,
        cache_key: str,
        shipment_id: str,
        shipment: Shipment | None = None,
    ) -> Optional[ShipmentStatusSchema]:
        shipment = shipment or await self._shipment_repo.get_by_id(shipment_id)
        if not shipment:
            return None

        latest_pos = await self._get_latest_candidate_position(shipment)
        freshness_warning = None

        domain_pos: Optional[DomainPosition] = None
        if latest_pos:
            domain_pos = DomainPosition(
                mmsi=latest_pos.mmsi,
                latitude=latest_pos.latitude,
                longitude=latest_pos.longitude,
                observed_at=latest_pos.observed_at,
                source=latest_pos.source,
            )

        eta_conf: ETAConfidence = domain_logic.compute_eta_confidence(
            declared_eta=shipment.declared_eta_date,
            latest_position=domain_pos,
            stale_after_seconds=settings.position_stale_after_seconds,
        )

        if eta_conf.freshness == FreshnessLevel.STALE:
            freshness_warning = (
                f"Position data is stale (last seen {latest_pos.observed_at.isoformat() if latest_pos else 'never'}). "
                "ETA estimate may not reflect actual vessel movement."
            )
        elif eta_conf.freshness == FreshnessLevel.UNKNOWN:
            freshness_warning = "No position data available. ETA is from carrier declaration only."

        candidate_vessels = self._to_candidate_vessel_schemas(shipment)

        result = ShipmentStatusSchema(
            shipment_id=shipment.id,
            booking_ref=shipment.booking_ref,
            carrier=shipment.carrier,
            status=shipment.status,
            declared_eta=shipment.declared_eta_date,
            latest_position=PositionSchema.model_validate(latest_pos) if latest_pos else None,
            eta_confidence=ETAConfidenceSchema(
                confidence=eta_conf.confidence,
                freshness=eta_conf.freshness.value,
                explanation=eta_conf.explanation,
                declared_eta=eta_conf.declared_eta,
            ),
            candidate_vessels=candidate_vessels,
            evidence_count=len(shipment.evidence_items),
            freshness_warning=freshness_warning,
        )
        await self._cache.set_json(
            cache_key,
            result.model_dump(mode="json"),
            settings.cache_shipment_status_ttl_seconds,
        )
        logger.info("cache_miss", key=cache_key)
        return result

    async def _get_or_build_shipment_history(
        self,
        cache_key: str,
        shipment_id: str,
        shipment: Shipment | None = None,
    ) -> Optional[ShipmentHistorySchema]:
        shipment = shipment or await self._shipment_repo.get_by_id(shipment_id)
        if not shipment:
            return None

        vessel_mmsi = None
        vessel_name = None
        track_points = []

        for sv in shipment.candidate_vessels:
            vessel = sv.vessel
            if vessel.mmsi:
                vessel_mmsi = vessel.mmsi
                vessel_name = vessel.name
                positions = await self._position_repo.get_history_for_mmsi(vessel.mmsi)
                for p in positions:
                    track_points.append(TrackPointSchema(
                        latitude=p.latitude,
                        longitude=p.longitude,
                        sog_knots=p.sog_knots,
                        cog_degrees=p.cog_degrees,
                        observed_at=p.observed_at,
                        source=p.source,
                    ))
            if track_points:
                break

        result = await self._session.execute(
            select(VoyageEvent)
            .where(VoyageEvent.shipment_id == shipment_id)
            .order_by(VoyageEvent.event_at.asc())
        )
        events_orm = result.scalars().all()
        events = [VoyageEventSchema.model_validate(e) for e in events_orm]

        history = ShipmentHistorySchema(
            shipment_id=shipment_id,
            vessel_mmsi=vessel_mmsi,
            vessel_name=vessel_name,
            track=sorted(track_points, key=lambda p: p.observed_at),
            events=events,
        )
        await self._cache.set_json(
            cache_key,
            history.model_dump(mode="json"),
            settings.cache_shipment_history_ttl_seconds,
        )
        logger.info("cache_miss", key=cache_key)
        return history

    def _to_candidate_vessel_schemas(self, shipment: Shipment) -> list[CandidateVesselSchema]:
        return [
            CandidateVesselSchema(
                vessel_id=sv.vessel_id,
                imo=sv.vessel.imo,
                mmsi=sv.vessel.mmsi,
                name=sv.vessel.name,
                is_primary=sv.is_primary,
            )
            for sv in shipment.candidate_vessels
        ]

    def _to_shipment_summary_schema(self, shipment: Shipment) -> ShipmentSummarySchema:
        return ShipmentSummarySchema(
            id=shipment.id,
            booking_ref=shipment.booking_ref,
            carrier=shipment.carrier,
            service_lane=shipment.service_lane,
            load_port=shipment.load_port,
            discharge_port=shipment.discharge_port,
            cargo_type=shipment.cargo_type,
            units=shipment.units,
            status=shipment.status,
            declared_departure_date=shipment.declared_departure_date,
            declared_eta_date=shipment.declared_eta_date,
            candidate_vessels=self._to_candidate_vessel_schemas(shipment),
        )

    def _to_shipment_detail_schema(self, shipment: Shipment) -> ShipmentDetailSchema:
        return ShipmentDetailSchema(
            **self._to_shipment_summary_schema(shipment).model_dump(),
            evidence=[EvidenceSchema.model_validate(e) for e in shipment.evidence_items],
        )

    async def _get_latest_candidate_position(self, shipment) -> LatestPosition | None:
        result = await self._session.execute(
            select(LatestPosition)
            .join(
                Vessel,
                (Vessel.mmsi == LatestPosition.mmsi)
                | ((Vessel.imo == LatestPosition.imo) & LatestPosition.imo.is_not(None)),
            )
            .join(ShipmentVessel, ShipmentVessel.vessel_id == Vessel.id)
            .where(ShipmentVessel.shipment_id == shipment.id)
            .order_by(ShipmentVessel.is_primary.desc(), LatestPosition.observed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def _build_manual_booking_ref(self, label: str, mmsi: str) -> str:
        compact = re.sub(r"[^A-Z0-9]+", "-", label.upper()).strip("-")
        compact = compact[:24] or "MANUAL"
        return f"{compact}-{mmsi[-6:]}"

    def _select_live_import_rows(self, rows: list, *, limit: int) -> list:
        now = datetime.now(timezone.utc)
        deduped: dict[tuple[str, str, str], object] = {}
        for row in sorted(
            rows,
            key=lambda item: (
                item.eta is None,
                abs((item.eta - now).total_seconds()) if item.eta else float("inf"),
                item.vessel_name or "",
            ),
        ):
            vessel_key = sanitize_text(row.vessel_name or row.vessel_imo or "unknown")
            dedupe_key = (row.carrier.lower(), vessel_key.lower(), row.port_locode)
            deduped.setdefault(dedupe_key, row)
            if len(deduped) >= limit:
                break
        return list(deduped.values())

    async def _upsert_live_carrier_shipment(self, row) -> Shipment:
        vessel_name = sanitize_text(row.vessel_name or row.vessel_imo or "Unnamed vessel")
        booking_ref = self._build_live_carrier_booking_ref(
            carrier=row.carrier,
            vessel_name=vessel_name,
            port_locode=row.port_locode,
        )
        shipment = await self._shipment_repo.get_by_booking_ref(booking_ref)
        if shipment is None:
            shipment = Shipment(
                id=self._build_live_carrier_shipment_id(booking_ref),
                booking_ref=booking_ref,
                carrier=row.carrier,
                service_lane="Live carrier schedule import",
                load_port=None,
                discharge_port=row.port_locode,
                cargo_type="carrier schedule tracked vessel",
                units=1,
                status="open",
                declared_departure_date=row.etd,
                declared_eta_date=row.eta,
            )
            await self._shipment_repo.save(shipment)
            logger.info(
                "carrier_live_shipment_created",
                shipment_id=shipment.id,
                booking_ref=booking_ref,
                carrier=row.carrier,
                vessel_name=vessel_name,
                port_locode=row.port_locode,
            )
        else:
            shipment.status = "open"
            shipment.service_lane = "Live carrier schedule import"
            shipment.discharge_port = row.port_locode
            shipment.cargo_type = "carrier schedule tracked vessel"
            shipment.units = 1
            shipment.declared_departure_date = row.etd
            shipment.declared_eta_date = row.eta
            logger.info(
                "carrier_live_shipment_updated",
                shipment_id=shipment.id,
                booking_ref=booking_ref,
                carrier=row.carrier,
                vessel_name=vessel_name,
                port_locode=row.port_locode,
            )

        vessel = await self._vessel_repo.get_or_create(row.vessel_imo, None, vessel_name)
        has_link = await self._session.scalar(
            select(ShipmentVessel.id)
            .where(ShipmentVessel.shipment_id == shipment.id)
            .where(ShipmentVessel.vessel_id == vessel.id)
            .limit(1)
        )
        existing_named_link = None
        if has_link is None:
            existing_named_link = await self._session.scalar(
                select(ShipmentVessel.id)
                .join(Vessel, Vessel.id == ShipmentVessel.vessel_id)
                .where(ShipmentVessel.shipment_id == shipment.id)
                .where(Vessel.name == vessel.name)
                .limit(1)
            )
        if has_link is None and existing_named_link is None:
            existing_primary = await self._session.scalar(
                select(ShipmentVessel.id)
                .where(ShipmentVessel.shipment_id == shipment.id)
                .where(ShipmentVessel.is_primary.is_(True))
                .limit(1)
            )
            self._session.add(
                ShipmentVessel(
                    shipment_id=shipment.id,
                    vessel_id=vessel.id,
                    is_primary=existing_primary is None,
                )
            )
            await self._session.flush()
            logger.info(
                "carrier_live_shipment_vessel_linked",
                shipment_id=shipment.id,
                vessel_id=vessel.id,
                vessel_name=vessel.name,
            )

        claim = (
            f"Live {row.carrier} schedule import is tracking {vessel_name} "
            f"toward {row.port_locode}"
            f"{f' on voyage {row.voyage_code}' if row.voyage_code else ''}."
        )
        await self._ensure_evidence_once(
            shipment_id=shipment.id,
            source=f"{row.carrier}_live_import",
            claim=claim,
        )
        return shipment

    async def _ensure_evidence_once(self, *, shipment_id: str, source: str, claim: str) -> None:
        result = await self._session.execute(
            select(Evidence.id)
            .where(Evidence.shipment_id == shipment_id)
            .where(Evidence.source == source)
            .where(Evidence.claim == claim)
            .limit(1)
        )
        if result.scalar_one_or_none() is not None:
            return
        self._session.add(
            Evidence(
                shipment_id=shipment_id,
                source=source,
                captured_at=datetime.now(timezone.utc),
                claim=claim,
            )
        )

    def _build_live_carrier_booking_ref(self, *, carrier: str, vessel_name: str, port_locode: str) -> str:
        carrier_slug = re.sub(r"[^A-Z0-9]+", "-", carrier.upper()).strip("-")
        vessel_slug = re.sub(r"[^A-Z0-9]+", "-", vessel_name.upper()).strip("-")[:36].rstrip("-")
        return f"LIVE-{carrier_slug}-{vessel_slug}-{port_locode}"

    def _build_live_carrier_shipment_id(self, booking_ref: str) -> str:
        digest = sha1(booking_ref.encode("utf-8")).hexdigest()[:8]
        return f"live-{digest}"

    def _build_clearance_checklist_schema(
        self,
        shipment_id: str,
        row: ClearanceChecklist | None,
    ) -> ClearanceChecklistSchema:
        if row is None:
            missing = ["form_m_approved", "bl_received", "paar_issued_at", "customs_duty_paid", "trucking_booked"]
            return ClearanceChecklistSchema(
                shipment_id=shipment_id,
                form_m_approved=False,
                bl_received=False,
                paar_submitted_at=None,
                paar_issued_at=None,
                customs_duty_paid=False,
                trucking_booked=False,
                notes="No checklist has been recorded yet.",
                completion_ratio=0.0,
                missing_items=missing,
            )

        checks = {
            "form_m_approved": bool(row.form_m_approved),
            "bl_received": bool(row.bl_received),
            "paar_issued_at": row.paar_issued_at is not None,
            "customs_duty_paid": bool(row.customs_duty_paid),
            "trucking_booked": bool(row.trucking_booked),
        }
        completed = sum(1 for value in checks.values() if value)
        missing = [key for key, value in checks.items() if not value]
        return ClearanceChecklistSchema(
            shipment_id=shipment_id,
            form_m_approved=row.form_m_approved,
            bl_received=row.bl_received,
            paar_submitted_at=row.paar_submitted_at,
            paar_issued_at=row.paar_issued_at,
            customs_duty_paid=row.customs_duty_paid,
            trucking_booked=row.trucking_booked,
            notes=row.notes,
            completion_ratio=round(completed / len(checks), 2),
            missing_items=missing,
        )


# ---------------------------------------------------------------------------
# SourceHealthService
# ---------------------------------------------------------------------------

class SourceHealthService:
    def __init__(self, session: AsyncSession, cache: CacheBackend | None = None) -> None:
        self._cache = cache or get_cache_backend()
        self._repo = SourceHealthRepository(session)

    async def list_health(self) -> list[SourceHealthSchema]:
        cache_key = "sources:health"
        cached = await self._cache.get_json(cache_key)
        if cached is not None:
            logger.info("cache_hit", key=cache_key)
            return [SourceHealthSchema.model_validate(item) for item in cached]

        rows = await self._repo.get_all()
        result = [SourceHealthSchema.model_validate(r) for r in rows]
        await self._cache.set_json(
            cache_key,
            [item.model_dump(mode="json") for item in result],
            settings.cache_source_health_ttl_seconds,
        )
        logger.info("cache_miss", key=cache_key)
        return result


class SourceCatalogService:
    async def list_readiness(self) -> list[SourceReadinessSchema]:
        return [
            SourceReadinessSchema(
                source=item.source,
                enabled=item.enabled,
                configured=item.configured,
                mode=item.mode,
                role=item.role,
                business_safe_default=item.business_safe_default,
                detail=item.detail,
            )
            for item in list_source_readiness()
        ]


class AppBootstrapService:
    def __init__(self) -> None:
        pass

    async def get_bootstrap(self, *, user_id: str) -> AppBootstrapSchema:
        from app.application.standby_services import StandbyAgentService

        async def load_shipments():
            async with AsyncSessionFactory() as session:
                return await ShipmentService(session).list_shipments()

        async def load_source_health():
            async with AsyncSessionFactory() as session:
                return await SourceHealthService(session).list_health()

        async def load_standby_agents():
            async with AsyncSessionFactory() as session:
                return await StandbyAgentService(session).list_agents(user_id=user_id)

        async def load_notifications():
            async with AsyncSessionFactory() as session:
                return await StandbyAgentService(session).list_notifications(user_id=user_id)

        async def load_agent_outputs():
            async with AsyncSessionFactory() as session:
                return await StandbyAgentService(session).list_outputs(user_id=user_id)

        shipments, source_health, standby_agents, notifications, agent_outputs = await asyncio.gather(
            load_shipments(),
            load_source_health(),
            load_standby_agents(),
            load_notifications(),
            load_agent_outputs(),
        )
        return AppBootstrapSchema(
            shipments=shipments,
            source_health=source_health,
            standby_agents=standby_agents,
            notifications=notifications,
            agent_outputs=agent_outputs,
        )


class KnowledgeBaseService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._embedding_service = embedding_service
        self._shipment_repo = ShipmentRepository(session)
        self._source_health_repo = SourceHealthRepository(session)
        self._revision_repo = ETARevisionRepository(session)
        self._port_obs_repo = PortObservationRepository(session)

    async def search(
        self,
        query: str,
        *,
        shipment_id: str | None = None,
        top_k: int = 5,
    ) -> KnowledgeSearchResponseSchema:
        tokens = _tokenize_query(query)
        snippets: list[KnowledgeSnippetSchema] = []

        if shipment_id:
            shipment = await self._shipment_repo.get_by_id(shipment_id)
            if shipment:
                for evidence in shipment.evidence_items:
                    snippets.append(
                        KnowledgeSnippetSchema(
                            source_name=evidence.source,
                            source_type="shipment_evidence",
                            content=evidence.claim,
                            relevance_score=_score_text(tokens, evidence.claim, bonus=1.5),
                            metadata={
                                "shipment_id": shipment.id,
                                "captured_at": evidence.captured_at.isoformat(),
                            },
                        )
                    )

                result = await self._session.execute(
                    select(VoyageEvent)
                    .where(VoyageEvent.shipment_id == shipment.id)
                    .order_by(VoyageEvent.event_at.desc())
                    .limit(25)
                )
                for event in result.scalars().all():
                    event_text = " ".join(
                        part for part in [event.event_type.replace("_", " "), event.details or ""] if part
                    )
                    snippets.append(
                        KnowledgeSnippetSchema(
                            source_name=event.source,
                            source_type="voyage_event",
                            content=event_text,
                            relevance_score=_score_text(tokens, event_text, bonus=1.0),
                            metadata={
                                "shipment_id": shipment.id,
                                "event_at": event.event_at.isoformat(),
                            },
                        )
                    )

                revisions = await self._revision_repo.list_for_shipment(shipment.id, limit=10)
                for revision in revisions:
                    revision_text = (
                        f"Carrier ETA revised from "
                        f"{revision.previous_eta.isoformat() if revision.previous_eta else 'unknown'} "
                        f"to {revision.new_eta.isoformat() if revision.new_eta else 'unknown'} "
                        f"({revision.delta_hours:+.2f}h)"
                        if revision.delta_hours is not None
                        else "Carrier ETA revision recorded."
                    )
                    snippets.append(
                        KnowledgeSnippetSchema(
                            source_name=revision.source,
                            source_type="eta_revision",
                            content=revision_text,
                            relevance_score=_score_text(tokens, revision_text, bonus=1.2),
                            metadata={
                                "shipment_id": shipment.id,
                                "revision_at": revision.revision_at.isoformat(),
                            },
                        )
                    )

                for sv in getattr(shipment, "candidate_vessels", []):
                    vessel = sv.vessel
                    observations = await self._port_obs_repo.list_for_shipment(
                        vessel_imo=vessel.imo,
                        vessel_mmsi=vessel.mmsi,
                        vessel_name=vessel.name,
                        port_locode=shipment.discharge_port,
                        limit=10,
                    )
                    for observation in observations:
                        observation_text = " ".join(
                            part
                            for part in [
                                observation.vessel_name or "",
                                observation.status or "",
                                observation.port_locode,
                                observation.detail or "",
                            ]
                            if part
                        )
                        snippets.append(
                            KnowledgeSnippetSchema(
                                source_name=observation.source,
                                source_type="port_observation",
                                content=observation_text,
                                relevance_score=_score_text(tokens, observation_text, bonus=1.1),
                                metadata={
                                    "shipment_id": shipment.id,
                                    "observed_at": observation.observed_at.isoformat(),
                                    "event_type": observation.event_type,
                                },
                            )
                        )

                snippets.extend(await self._document_snippets(query, tokens, shipment_id=shipment.id, bonus=1.4))

        else:
            snippets.extend(await self._document_snippets(query, tokens, shipment_id=None, bonus=1.2))

        for readiness in list_source_readiness():
            policy_text = f"{readiness.role}. {readiness.detail}"
            snippets.append(
                KnowledgeSnippetSchema(
                    source_name=readiness.source,
                    source_type="source_policy",
                    content=policy_text,
                    relevance_score=_score_text(tokens, policy_text, bonus=0.6),
                    metadata={
                        "mode": readiness.mode,
                        "configured": readiness.configured,
                        "enabled": readiness.enabled,
                    },
                )
            )

        for health in await self._source_health_repo.get_all():
            health_text = " ".join(
                part
                for part in [
                    health.source,
                    health.source_class,
                    health.automation_safety,
                    health.degraded_reason or "",
                ]
                if part
            )
            snippets.append(
                KnowledgeSnippetSchema(
                    source_name=health.source,
                    source_type="source_health",
                    content=health_text,
                    relevance_score=_score_text(tokens, health_text, bonus=0.4),
                    metadata={
                        "source_status": health.source_status,
                        "last_success_at": health.last_success_at.isoformat() if health.last_success_at else None,
                    },
                )
            )

        ranked = sorted(
            (snippet for snippet in snippets if snippet.relevance_score > 0),
            key=lambda item: item.relevance_score,
            reverse=True,
        )

        if not ranked:
            ranked = sorted(
                snippets,
                key=lambda item: (
                    item.source_type != "shipment_evidence",
                    item.source_type != "voyage_event",
                    item.source_name,
                ),
            )

        return KnowledgeSearchResponseSchema(
            query=query,
            shipment_id=shipment_id,
            snippets=ranked[:top_k],
            retrieved_at=datetime.now(timezone.utc),
        )

    async def _document_snippets(
        self,
        query: str,
        tokens: list[str],
        *,
        shipment_id: str | None,
        bonus: float,
    ) -> list[KnowledgeSnippetSchema]:
        chunks = await self._vector_ranked_chunks(query, shipment_id=shipment_id)
        retrieval_mode = "vector"
        if not chunks:
            chunks = await self._lexical_chunks(shipment_id=shipment_id)
            retrieval_mode = "lexical"

        snippets: list[KnowledgeSnippetSchema] = []
        total_chunks = max(len(chunks), 1)
        for index, chunk in enumerate(chunks):
            doc_text = " ".join(part for part in [chunk.title or "", chunk.content] if part)
            lexical_score = _score_text(tokens, doc_text, bonus=bonus)
            semantic_score = _semantic_rank_score(index, total_chunks) if retrieval_mode == "vector" else 0.0
            source_weight = _document_source_type_weight(chunk.source_type)
            if retrieval_mode == "vector":
                relevance_score = round((semantic_score * 0.65) + (lexical_score * 0.35) + source_weight, 3)
            else:
                relevance_score = round(lexical_score + source_weight, 3)
            snippets.append(
                KnowledgeSnippetSchema(
                    source_name=chunk.source_name,
                    source_type=chunk.source_type,
                    content=doc_text,
                    relevance_score=relevance_score,
                    metadata={
                        "shipment_id": chunk.shipment_id,
                        "title": chunk.title,
                        "retrieval_mode": retrieval_mode,
                        "semantic_score": semantic_score if retrieval_mode == "vector" else None,
                        "lexical_score": lexical_score,
                        "source_weight": source_weight,
                    },
                )
            )
        return snippets

    async def _vector_ranked_chunks(self, query: str, *, shipment_id: str | None) -> list[DocumentChunk]:
        if not self._embedding_service.is_available() or not self._embedding_service.supports_vector_search():
            return []

        query_vector = await self._embedding_service.embed_text(query)
        if not query_vector:
            return []

        filters = [DocumentChunk.embedding.is_not(None)]
        if shipment_id:
            filters.append((DocumentChunk.shipment_id == shipment_id) | (DocumentChunk.shipment_id.is_(None)))

        distance = DocumentChunk.embedding.cosine_distance(query_vector)
        stmt = (
            select(DocumentChunk)
            .where(*filters)
            .order_by(distance.asc(), DocumentChunk.ingested_at.desc())
            .limit(max(settings.knowledge_vector_top_k, 20))
        )
        try:
            result = await self._session.execute(stmt)
        except Exception as exc:
            logger.warning("knowledge_vector_query_failed", shipment_id=shipment_id, error=str(exc))
            return []
        return result.scalars().all()

    async def _lexical_chunks(self, *, shipment_id: str | None) -> list[DocumentChunk]:
        if shipment_id:
            stmt = (
                select(DocumentChunk)
                .where((DocumentChunk.shipment_id == shipment_id) | (DocumentChunk.shipment_id.is_(None)))
                .order_by(DocumentChunk.ingested_at.desc())
                .limit(50)
            )
        else:
            stmt = select(DocumentChunk).order_by(DocumentChunk.ingested_at.desc()).limit(50)
        result = await self._session.execute(stmt)
        return result.scalars().all()


def _tokenize_query(query: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 2]


def _score_text(tokens: list[str], text: str, *, bonus: float = 0.0) -> float:
    haystack = text.lower()
    score = 0.0
    for token in tokens:
        if token in haystack:
            score += 1.0
    return score + bonus if score > 0 else 0.0


def _semantic_rank_score(index: int, total: int) -> float:
    return max(0.2, 1.0 - (index / max(total, 1)))


def _document_source_type_weight(source_type: str) -> float:
    return {
        "analyst_doc": 0.25,
        "uploaded_doc": 0.2,
        "scenario_note": 0.15,
        "reference_doc": 0.1,
    }.get(source_type, 0.05)


# ---------------------------------------------------------------------------
# GeoService — PostGIS spatial queries
# ---------------------------------------------------------------------------

class GeoService:
    """Wraps GeoRepository for API/tool consumption with Pydantic schemas."""

    def __init__(self, session: AsyncSession) -> None:
        from app.infrastructure.repositories import GeoRepository
        self._geo_repo = GeoRepository(session)
        self._session = session

    async def find_nearby_vessels(
        self,
        latitude: float,
        longitude: float,
        radius_nm: float = 50.0,
        limit: int = 20,
    ) -> dict:
        from app.schemas.responses import NearbyVesselsResponseSchema
        vessels = await self._geo_repo.find_vessels_within_radius(
            latitude, longitude, radius_nm=radius_nm, limit=limit
        )
        return NearbyVesselsResponseSchema(
            center_latitude=latitude,
            center_longitude=longitude,
            radius_nm=radius_nm,
            vessel_count=len(vessels),
            vessels=vessels,
        )

    async def find_nearest_port(
        self,
        latitude: float,
        longitude: float,
        limit: int = 3,
    ) -> dict:
        from app.schemas.responses import NearestPortResponseSchema
        ports = await self._geo_repo.find_nearest_port(latitude, longitude, limit=limit)
        return NearestPortResponseSchema(
            query_latitude=latitude,
            query_longitude=longitude,
            ports=ports,
        )

    async def check_vessel_port_proximity(self, mmsi: str) -> dict | None:
        return await self._geo_repo.get_vessel_port_proximity(mmsi)

    async def check_shipment_port_proximity(self, shipment_id: str) -> dict | None:
        """Check port proximity for all candidate vessels of a shipment."""
        from app.infrastructure.repositories import ShipmentRepository, PositionRepository
        shipment_repo = ShipmentRepository(self._session)
        position_repo = PositionRepository(self._session)

        shipment = await shipment_repo.get_by_id(shipment_id)
        if shipment is None:
            return None

        vessels = await shipment_repo.get_candidate_vessels(shipment_id)
        results = []

        for sv, vessel in vessels:
            mmsi = vessel.mmsi
            if not mmsi:
                continue
            proximity = await self._geo_repo.get_vessel_port_proximity(mmsi)
            if proximity:
                results.append(proximity)

        return {
            "shipment_id": shipment_id,
            "vessel_proximities": results,
        }

    async def list_reference_ports(self) -> list[dict]:
        return await self._geo_repo.list_reference_ports()
