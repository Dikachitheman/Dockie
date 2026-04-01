"""
Fixture ingest pipeline.

Loads challenge_resource_pack.json and challenge_malicious_payload.json.
Steps:
  1. Persist raw payload to raw_events (always)
  2. Scan for hostile content → quarantine if found
  3. Validate and normalize → quarantine if invalid
  4. Upsert normalized records; skip stale positions
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import strip_control_chars
from app.infrastructure.normalizer import (
    detect_hostile_content,
    normalize_evidence,
    normalize_position,
    normalize_shipment,
    normalize_vessel,
    normalize_voyage_event,
)
from app.infrastructure.repositories import (
    PositionRepository,
    RawEventRepository,
    ShipmentRepository,
    SourceHealthRepository,
    VesselRepository,
)
from app.infrastructure.cache import invalidate_shipment_cache
from app.infrastructure.source_policy import get_policy_or_default
from app.models.orm import (
    Evidence,
    QuarantinedEvent,
    RawEvent,
    ShipmentVessel,
    SourceHealth,
    VoyageEvent,
    VoyageSignal,
)

logger = get_logger(__name__)
settings = get_settings()


def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _db_safe_payload(value: Any) -> Any:
    """
    Recursively strip control characters that PostgreSQL JSONB cannot store.

    We still scan the original payload for hostile content first; this only
    produces an inert storage-safe copy for raw/quarantine persistence.
    """
    if isinstance(value, str):
        return strip_control_chars(value)
    if isinstance(value, dict):
        return {k: _db_safe_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_db_safe_payload(item) for item in value]
    return value


def _serialize_raw_payload(payload: dict[str, Any]) -> str:
    """Store a textual JSON form that preserves escapes such as \\u0000."""
    return json.dumps(payload, ensure_ascii=True)


# ---------------------------------------------------------------------------
# Source health seed data
# ---------------------------------------------------------------------------

SOURCE_HEALTH_SEEDS = [
    ("aisstream", "public_api_terms", "moderate", True, 3600),
    ("grimaldi", "public_api_terms", "fragile_scraper", True, 604800),
    ("sallaum", "public_api_terms", "fragile_scraper", True, 604800),
    ("orbcomm", "noncommercial_or_license_limited", "moderate", False, 7200),
    ("global_fishing_watch", "public_api_terms", "moderate", True, 86400),
    ("official_sanctions", "open_data", "high", True, 86400),
    ("nigerian_ports", "analyst_reference_only", "validation_required", False, 86400),
    ("carrier_schedule", "public_api_terms", "fragile_scraper", True, 604800),
    ("historical_ais", "open_data", "high", True, 604800),
    ("untrusted_manual_import", "analyst_reference_only", "human_in_loop", False, 0),
]


async def _seed_source_health(session: AsyncSession) -> None:
    repo = SourceHealthRepository(session)
    for source, s_class, safety, biz_safe, stale_after in SOURCE_HEALTH_SEEDS:
        existing = await repo.get_by_source(source)
        if existing:
            continue
        record = SourceHealth(
            id=_uid(),
            source=source,
            source_class=s_class,
            automation_safety=safety,
            business_safe_default=biz_safe,
            source_status="healthy",
            last_success_at=_now(),
            stale_after_seconds=stale_after,
        )
        session.add(record)
    await session.flush()
    logger.info("source_health_seeded")


# ---------------------------------------------------------------------------
# Raw event persistence
# ---------------------------------------------------------------------------

async def _persist_raw(
    session: AsyncSession,
    source: str,
    event_type: str,
    payload: dict[str, Any],
    received_at: datetime | None = None,
    raw_payload_text: str | None = None,
) -> RawEvent:
    raw = RawEvent(
        id=_uid(),
        source=source,
        event_type=event_type,
        received_at=received_at or _now(),
        payload=_db_safe_payload(payload),
        raw_payload_text=raw_payload_text or _serialize_raw_payload(payload),
    )
    session.add(raw)
    await session.flush()
    return raw


async def _quarantine(
    session: AsyncSession,
    raw_event_id: str | None,
    source: str,
    reason: str,
    payload: dict[str, Any],
    raw_payload_text: str | None = None,
) -> None:
    q = QuarantinedEvent(
        id=_uid(),
        raw_event_id=raw_event_id,
        source=source,
        reason=reason,
        payload=_db_safe_payload(payload),
        raw_payload_text=raw_payload_text or _serialize_raw_payload(payload),
    )
    session.add(q)
    await session.flush()
    logger.warning("payload_quarantined", source=source, reason=reason[:120])


# ---------------------------------------------------------------------------
# Resource pack ingestion
# ---------------------------------------------------------------------------

async def ingest_resource_pack(session: AsyncSession, path: Path) -> dict[str, int]:
    logger.info("ingest_resource_pack_start", path=str(path))
    data: dict[str, Any] = json.loads(path.read_text())

    counters = {
        "shipments": 0,
        "vessels": 0,
        "positions": 0,
        "history_points": 0,
        "voyage_events": 0,
        "quarantined": 0,
        "skipped_stale": 0,
        "already_current": 0,
    }

    shipment_repo = ShipmentRepository(session)
    vessel_repo = VesselRepository(session)
    position_repo = PositionRepository(session)
    mmsi_to_shipment_ids = await _load_mmsi_to_shipment_ids(session)
    invalidated_shipment_ids: set[str] = set()

    # ---- Shipments ----
    for raw_ship in data.get("shipments", []):
        raw_ev = await _persist_raw(session, raw_ship.get("carrier", "unknown"), "shipment", raw_ship)

        shipment, err = normalize_shipment(raw_ship, raw_ev.id)
        if err:
            await _quarantine(session, raw_ev.id, "carrier", err, raw_ship)
            counters["quarantined"] += 1
            continue

        # Check for existing
        existing = await shipment_repo.get_by_id(shipment.id)
        if not existing:
            session.add(shipment)
            await session.flush()
            counters["shipments"] += 1
        else:
            shipment = existing

        # Evidence
        for ev_raw in raw_ship.get("evidence", []):
            ev, ev_err = normalize_evidence(ev_raw, shipment.id)
            if ev_err:
                await _quarantine(session, raw_ev.id, "carrier", ev_err, ev_raw)
                counters["quarantined"] += 1
            else:
                session.add(ev)
                await session.flush()

        # Candidate vessels
        for i, vraw in enumerate(raw_ship.get("candidate_vessels", [])):
            vessel, v_err = normalize_vessel(vraw)
            if v_err:
                logger.warning("vessel_normalize_failed", reason=v_err)
                continue

            db_vessel = await vessel_repo.get_or_create(vessel.imo, vessel.mmsi, vessel.name)
            counters["vessels"] += 1

            # Link shipment <-> vessel
            from sqlalchemy import select
            result = await session.execute(
                select(ShipmentVessel).where(
                    ShipmentVessel.shipment_id == shipment.id,
                    ShipmentVessel.vessel_id == db_vessel.id,
                )
            )
            if not result.scalar_one_or_none():
                sv = ShipmentVessel(
                    id=_uid(),
                    shipment_id=shipment.id,
                    vessel_id=db_vessel.id,
                    is_primary=(i == 0),
                )
                session.add(sv)
                await session.flush()

    # ---- Live positions ----
    position_counts = await ingest_position_payloads(
        session,
        data.get("vessel_positions", []),
        commit=False,
        mmsi_to_shipment_ids=mmsi_to_shipment_ids,
        invalidated_shipment_ids=invalidated_shipment_ids,
        position_repo=position_repo,
    )
    counters["positions"] += position_counts["positions"]
    counters["quarantined"] += position_counts["quarantined"]
    counters["skipped_stale"] += position_counts["skipped_stale"]
    counters["already_current"] += position_counts["already_current"]

    # ---- Vessel history ----
    for vessel_history in data.get("vessel_history", []):
        mmsi = str(vessel_history.get("mmsi", ""))
        imo = str(vessel_history.get("imo", ""))
        vessel_name = vessel_history.get("vessel_name", "")

        for point in vessel_history.get("points", []):
            point_data = {**point, "mmsi": mmsi, "imo": imo, "vessel_name": vessel_name}
            raw_ev = await _persist_raw(session, point.get("source", "historical_ais"), "history_point", point_data)

            pos, err = normalize_position(point_data, raw_ev.id)
            if err:
                await _quarantine(session, raw_ev.id, "historical_ais", err, point_data)
                counters["quarantined"] += 1
                continue

            await position_repo.save_raw(pos)
            counters["history_points"] += 1
            await _invalidate_mmsi_shipments(
                pos.mmsi,
                mmsi_to_shipment_ids,
                invalidated_shipment_ids,
            )

        # Voyage events
        for ev_raw in vessel_history.get("events", []):
            # Find matching shipment by IMO/MMSI
            shipment_id = await _find_shipment_for_vessel(session, imo, mmsi)
            ev, err = normalize_voyage_event(ev_raw, shipment_id=shipment_id, vessel_imo=imo or None)
            if err:
                logger.warning("voyage_event_normalize_failed", reason=err)
                continue
            session.add(ev)
            await session.flush()
            counters["voyage_events"] += 1

    # ---- Malformed / stale payloads ----
    for bad_payload in data.get("malformed_and_stale_payloads", []):
        source = bad_payload.get("source", "unknown")
        received_raw = bad_payload.get("received_at")
        from app.infrastructure.normalizer import _parse_datetime
        received_at = _parse_datetime(received_raw) or _now()

        raw_ev = await _persist_raw(session, source, bad_payload.get("kind", "unknown"), bad_payload, received_at)

        kind = bad_payload.get("kind")
        reasons = []

        if kind == "stale":
            reasons.append("Payload marked stale by fixture metadata")
        elif kind == "malformed":
            reasons.append("Payload marked malformed by fixture metadata")

        # Attempt full normalization to surface specific errors
        inner = bad_payload.get("payload", {})
        if inner:
            _, pos_err = normalize_position(
                {**inner, "observed_at": inner.get("MetaData", {}).get("time_utc")},
                raw_ev.id
            )
            if pos_err:
                reasons.append(pos_err)

        if reasons:
            await _quarantine(session, raw_ev.id, source, "; ".join(reasons), bad_payload)
            counters["quarantined"] += 1

    await session.commit()
    from app.infrastructure.cache import invalidate_cache_prefix
    await invalidate_cache_prefix("shipments:list")
    logger.info("ingest_resource_pack_complete", **counters)
    return counters


async def ingest_position_payloads(
    session: AsyncSession,
    raw_positions: list[dict[str, Any]],
    *,
    commit: bool = False,
    mmsi_to_shipment_ids: dict[str, list[str]] | None = None,
    invalidated_shipment_ids: set[str] | None = None,
    position_repo: PositionRepository | None = None,
) -> dict[str, int]:
    counters = {
        "positions": 0,
        "quarantined": 0,
        "skipped_stale": 0,
        "already_current": 0,
    }
    local_position_repo = position_repo or PositionRepository(session)
    local_mmsi_to_shipment_ids = mmsi_to_shipment_ids or await _load_mmsi_to_shipment_ids(session)
    local_invalidated_shipment_ids = invalidated_shipment_ids or set()

    for raw_pos in raw_positions:
        source = raw_pos.get("source", "unknown")
        raw_ev = await _persist_raw(session, source, "position", raw_pos)

        pos, err = normalize_position(raw_pos, raw_ev.id)
        if err:
            await _quarantine(session, raw_ev.id, source, err, raw_pos)
            counters["quarantined"] += 1
            continue

        save_result = await local_position_repo.save_with_status(pos)
        if save_result.status in {"inserted", "updated_latest"}:
            counters["positions"] += 1
            await _invalidate_mmsi_shipments(
                pos.mmsi,
                local_mmsi_to_shipment_ids,
                local_invalidated_shipment_ids,
            )
        elif save_result.status == "already_current":
            counters["already_current"] += 1
            logger.info("position_already_current", mmsi=pos.mmsi, observed_at=pos.observed_at.isoformat())
        else:
            counters["skipped_stale"] += 1
            logger.info("position_skipped_stale", mmsi=pos.mmsi, observed_at=pos.observed_at.isoformat())

    if commit:
        await session.commit()
        from app.infrastructure.cache import invalidate_cache_prefix
        await invalidate_cache_prefix("shipments:list")

    return counters


async def ingest_position_snapshot_file(
    session: AsyncSession,
    path: Path,
    *,
    commit: bool = False,
) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    positions = payload.get("positions", []) if isinstance(payload, dict) else []
    if not isinstance(positions, list):
        positions = []
    return await ingest_position_payloads(session, positions, commit=commit)


async def _load_mmsi_to_shipment_ids(session: AsyncSession) -> dict[str, list[str]]:
    from app.models.orm import Shipment, ShipmentVessel, Vessel

    result = await session.execute(
        select(Vessel.mmsi, Shipment.id)
        .join(ShipmentVessel, ShipmentVessel.vessel_id == Vessel.id)
        .join(Shipment, Shipment.id == ShipmentVessel.shipment_id)
        .where(Vessel.mmsi.is_not(None))
    )

    mapping: dict[str, list[str]] = {}
    for mmsi, shipment_id in result.all():
        if not mmsi or not shipment_id:
            continue
        mapping.setdefault(str(mmsi), []).append(str(shipment_id))
    return mapping


async def _invalidate_mmsi_shipments(
    mmsi: str,
    mmsi_to_shipment_ids: dict[str, list[str]],
    invalidated_shipment_ids: set[str],
) -> None:
    for shipment_id in mmsi_to_shipment_ids.get(mmsi, []):
        if shipment_id in invalidated_shipment_ids:
            continue
        await invalidate_shipment_cache(shipment_id)
        invalidated_shipment_ids.add(shipment_id)


async def _find_shipment_for_vessel(session: AsyncSession, imo: str, mmsi: str) -> str | None:
    """Find a shipment ID linked to a vessel with given IMO or MMSI."""
    from sqlalchemy import select
    from app.models.orm import Vessel, ShipmentVessel
    result = await session.execute(
        select(ShipmentVessel.shipment_id)
        .join(Vessel, ShipmentVessel.vessel_id == Vessel.id)
        .where((Vessel.imo == imo) | (Vessel.mmsi == mmsi))
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return str(row) if row else None


# ---------------------------------------------------------------------------
# Malicious payload ingestion
# ---------------------------------------------------------------------------

async def ingest_malicious_payload(session: AsyncSession, path: Path) -> None:
    logger.info("ingest_malicious_payload_start", path=str(path))
    raw_text = path.read_text()
    data: dict[str, Any] = json.loads(raw_text)

    source = data.get("source", "untrusted_manual_import")
    received_raw = data.get("received_at")
    from app.infrastructure.normalizer import _parse_datetime
    received_at = _parse_datetime(received_raw) or _now()

    # Always persist the raw payload first — inert storage
    raw_ev = await _persist_raw(
        session,
        source,
        "malicious_test",
        data,
        received_at,
        raw_payload_text=raw_text,
    )
    logger.info("malicious_raw_persisted", raw_id=raw_ev.id)

    # Scan for hostile content
    payload = data.get("payload", data)
    findings = detect_hostile_content(payload)

    if findings:
        reasons = "HOSTILE CONTENT: " + " | ".join(findings[:5])
        await _quarantine(session, raw_ev.id, source, reasons, data, raw_payload_text=raw_text)
        logger.warning(
            "malicious_payload_quarantined",
            finding_count=len(findings),
            sample=findings[0][:80],
        )
    else:
        # Even if no hostile patterns, untrusted_manual_import is always quarantined
        await _quarantine(
            session,
            raw_ev.id,
            source,
            "Source policy: untrusted_manual_import requires analyst review",
            data,
            raw_payload_text=raw_text,
        )

    await session.commit()
    logger.info("ingest_malicious_payload_complete")


# ---------------------------------------------------------------------------
# Full ingest runner
# ---------------------------------------------------------------------------

async def run_full_ingest(session: AsyncSession) -> None:
    await _seed_source_health(session)
    await session.commit()

    pack_path = Path(settings.resource_pack_path)
    if pack_path.exists():
        await ingest_resource_pack(session, pack_path)
    else:
        logger.warning("resource_pack_not_found", path=str(pack_path))

    malicious_path = Path(settings.malicious_payload_path)
    if malicious_path.exists():
        await ingest_malicious_payload(session, malicious_path)
    else:
        logger.warning("malicious_payload_not_found", path=str(malicious_path))

    from app.infrastructure.simulated_ingest import ingest_simulated_baseline

    await ingest_simulated_baseline(session)
