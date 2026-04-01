"""
Simulated data ingest helpers.

Loads fake operational state, fake document corpora, and manual scenario packs
so the app can be demoed without live external sources.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.embeddings import apply_embeddings_to_chunks
from app.infrastructure.cache import invalidate_cache_prefix
from app.infrastructure.ingest import ingest_position_payloads
from app.infrastructure.normalizer import _parse_datetime
from app.models.orm import (
    CarrierPerformanceMetric,
    CarrierSchedule,
    ClearanceChecklist,
    DemurrageTariff,
    DocumentChunk,
    ETARevisionLog,
    FXRate,
    PortCongestionReading,
    PortCongestionSeasonality,
    PortObservation,
    Shipment,
)

logger = get_logger(__name__)


def simulated_root() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "simulated"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _chunk_text(text: str, chunk_size: int = 420) -> list[str]:
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []
    paragraphs = [part.strip() for part in normalized.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip()
        if current and len(candidate) > chunk_size:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def ingest_simulated_baseline(session: AsyncSession, root: Path | None = None) -> None:
    base = root or simulated_root()
    if not base.exists():
        logger.warning("simulated_root_missing", path=str(base))
        return

    await _ingest_baseline_tables(session, base / "baseline_intelligence.json")
    await _ingest_eta_revisions(session, base / "eta_revisions" / "run_001.json")
    await _ingest_port_observations(session, base / "port_observations" / "run_001.json")
    await _ingest_carrier_schedules(session, base / "carrier_schedule_updates" / "run_001.json")
    await _ingest_reference_docs(session, base)
    await session.commit()
    await invalidate_cache_prefix("shipments:")
    await invalidate_cache_prefix("sources:")


async def ingest_position_snapshot(session: AsyncSession, path: Path) -> None:
    if not path.exists():
        return
    payload = _load_json(path)
    positions = payload.get("positions", []) if isinstance(payload, dict) else []
    if isinstance(positions, list) and positions:
        await ingest_position_payloads(session, positions, commit=False)


async def apply_simulated_scenario(session: AsyncSession, scenario_name: str, root: Path | None = None) -> None:
    base = root or simulated_root()
    path = base / "scenarios" / f"{scenario_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Scenario not found: {path}")

    data = _load_json(path)
    await _apply_shipment_updates(session, data.get("shipment_updates", []))
    await _ingest_eta_revisions_payload(session, data.get("eta_revisions", []))
    await _ingest_port_observations_payload(session, data.get("port_observations", []))
    await _ingest_port_congestion_payload(session, data.get("port_congestion_readings", []))
    await _upsert_clearance_checklists(session, data.get("clearance_checklists", []))
    await _ingest_knowledge_docs(session, data.get("knowledge_docs", []))
    positions = data.get("positions", [])
    if isinstance(positions, list) and positions:
        await ingest_position_payloads(session, positions, commit=False)
    await session.commit()
    await invalidate_cache_prefix("shipments:")


async def _ingest_baseline_tables(session: AsyncSession, path: Path) -> None:
    if not path.exists():
        return
    data = _load_json(path)
    await _upsert_clearance_checklists(session, data.get("clearance_checklists", []))
    await _replace_table(session, PortCongestionReading, data.get("port_congestion_readings", []))
    await _replace_table(session, PortCongestionSeasonality, data.get("port_congestion_seasonality", []))
    await _replace_table(session, CarrierPerformanceMetric, data.get("carrier_performance_metrics", []))
    await _replace_table(session, DemurrageTariff, data.get("demurrage_tariffs", []))
    await _replace_table(session, FXRate, data.get("fx_rates", []))


async def _replace_table(session: AsyncSession, model, rows: list[dict[str, Any]]) -> None:
    await session.execute(delete(model))
    for row in rows:
        payload = dict(row)
        for key, value in list(payload.items()):
            if key.endswith("_at") or key.endswith("_from") or key == "observed_at":
                payload[key] = _parse_datetime(value) if isinstance(value, str) else value
        session.add(model(**payload))
    await session.flush()


async def _upsert_clearance_checklists(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        shipment_id = row["shipment_id"]
        existing = await session.get(ClearanceChecklist, shipment_id)
        payload = dict(row)
        for key in ("paar_submitted_at", "paar_issued_at"):
            if payload.get(key):
                payload[key] = _parse_datetime(payload[key])
        if existing is None:
            session.add(ClearanceChecklist(**payload))
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
    await session.flush()


async def _ingest_eta_revisions(session: AsyncSession, path: Path) -> None:
    if path.exists():
        await _ingest_eta_revisions_payload(session, _load_json(path).get("revisions", []))


async def _ingest_eta_revisions_payload(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        previous_eta = _parse_datetime(row.get("previous_eta"))
        new_eta = _parse_datetime(row.get("new_eta"))
        delta_hours = None
        if previous_eta and new_eta:
            delta_hours = round((new_eta - previous_eta).total_seconds() / 3600, 2)
        session.add(
            ETARevisionLog(
                shipment_id=row.get("shipment_id"),
                carrier=row.get("carrier"),
                revision_at=_parse_datetime(row.get("revision_at")),
                previous_eta=previous_eta,
                new_eta=new_eta,
                delta_hours=delta_hours,
                source=row.get("source", "simulated"),
            )
        )
    await session.flush()


async def _ingest_port_observations(session: AsyncSession, path: Path) -> None:
    if path.exists():
        await _ingest_port_observations_payload(session, _load_json(path).get("observations", []))


async def _ingest_port_observations_payload(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        session.add(
            PortObservation(
                port_locode=row["port_locode"],
                terminal_name=row.get("terminal_name"),
                vessel_name=row.get("vessel_name"),
                vessel_imo=row.get("vessel_imo"),
                vessel_mmsi=row.get("vessel_mmsi"),
                status=row.get("status"),
                event_type=row.get("event_type", "observed"),
                detail=row.get("detail"),
                source=row.get("source", "simulated_port_watch"),
                observed_at=_parse_datetime(row["observed_at"]),
            )
        )
    await session.flush()


async def _ingest_port_congestion_payload(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        session.add(
            PortCongestionReading(
                port_locode=row["port_locode"],
                delay_days=row["delay_days"],
                queue_vessels=row.get("queue_vessels"),
                source=row.get("source", "simulated"),
                detail=row.get("detail"),
                observed_at=_parse_datetime(row["observed_at"]),
            )
        )
    await session.flush()


async def _ingest_carrier_schedules(session: AsyncSession, path: Path) -> None:
    if not path.exists():
        return
    rows = _load_json(path).get("rows", [])
    for row in rows:
        session.add(
            CarrierSchedule(
                carrier=row["carrier"],
                voyage_code=row.get("voyage_code"),
                vessel_name=row.get("vessel_name"),
                vessel_imo=row.get("vessel_imo"),
                port_locode=row["port_locode"],
                etd=_parse_datetime(row.get("etd")),
                eta=_parse_datetime(row.get("eta")),
                source=row.get("source", "simulated_carrier_page"),
                scraped_at=_parse_datetime(row["scraped_at"]),
            )
        )
    await session.flush()


async def _apply_shipment_updates(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        shipment = await session.get(Shipment, row["shipment_id"])
        if shipment is None:
            continue
        for field in ("status", "declared_eta_date", "declared_departure_date"):
            if field in row:
                value = row[field]
                if field.endswith("_date") and isinstance(value, str):
                    value = _parse_datetime(value)
                setattr(shipment, field, value)
    await session.flush()


async def _ingest_reference_docs(session: AsyncSession, base: Path) -> None:
    doc_roots = [
        (base / "docs", "reference_doc"),
        (base / "generated_analyst_docs", "analyst_doc"),
        (base / "user_uploads", "uploaded_doc"),
    ]
    for root, source_type in doc_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8")
            shipment_id = None
            if source_type == "uploaded_doc" and path.stem.startswith("ship-"):
                shipment_id = path.stem.split("_")[0]
            await _replace_document_source(
                session,
                source_name=str(path.relative_to(base)).replace("\\", "/"),
                source_type=source_type if source_type != "reference_doc" else path.parent.name,
                content=content,
                title=path.stem.replace("_", " "),
                shipment_id=shipment_id,
            )


async def _ingest_knowledge_docs(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        await _replace_document_source(
            session,
            source_name=row["source_name"],
            source_type=row.get("source_type", "scenario_note"),
            content=row["content"],
            title=row.get("title"),
            shipment_id=row.get("shipment_id"),
            metadata=row.get("metadata"),
        )


async def _replace_document_source(
    session: AsyncSession,
    *,
    source_name: str,
    source_type: str,
    content: str,
    title: str | None = None,
    shipment_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    await session.execute(delete(DocumentChunk).where(DocumentChunk.source_name == source_name))
    created_chunks: list[DocumentChunk] = []
    for index, chunk in enumerate(_chunk_text(content), start=1):
        document_chunk = DocumentChunk(
            source_name=source_name,
            source_type=source_type,
            shipment_id=shipment_id,
            title=title or source_name,
            content=chunk,
            chunk_metadata={**(metadata or {}), "chunk_index": index},
        )
        created_chunks.append(document_chunk)
        session.add(document_chunk)
    await session.flush()
    await apply_embeddings_to_chunks(created_chunks)
    await session.flush()
