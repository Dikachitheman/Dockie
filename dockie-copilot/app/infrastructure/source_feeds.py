"""
Fetch, parse, and persist external source overlays.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
import json
import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import sanitize_text, sanitize_url
from app.infrastructure.normalizer import _parse_datetime
from app.models.orm import CarrierSchedule, ETARevisionLog, Evidence, PortObservation, Shipment, ShipmentVessel, Vessel, VoyageEvent

settings = get_settings()
logger = get_logger(__name__)


PORT_LOCODE_ALIASES = {
    "lagos": "NGLOS",
    "tin can": "NGTIN",
    "tin can island": "NGTIN",
    "apapa": "NGAPP",
    "cotonou": "BJCOO",
    "tema": "GHTEM",
    "lome": "TGLFW",
    "dakar": "SNDKR",
    "freeport": "BSFPO",
    "jacksonville": "USJAX",
    "baltimore": "USBAL",
    "brunswick": "USSSI",
    "davisville": "USDVV",
    "newark": "USNWK",
}

TERMINAL_PORT_ALIASES = {
    "apm terminal": "NGAPP",
    "tin can": "NGTIN",
    "ports and cargo": "NGTIN",
    "ptml": "NGTIN",
    "five star": "NGAPP",
}


@dataclass(frozen=True)
class ParsedCarrierSchedule:
    carrier: str
    voyage_code: str | None
    vessel_name: str | None
    vessel_imo: str | None
    port_locode: str
    etd: datetime | None
    eta: datetime | None
    source_url: str | None
    scraped_at: datetime


@dataclass(frozen=True)
class ParsedPortObservation:
    port_locode: str
    terminal_name: str | None
    vessel_name: str | None
    vessel_imo: str | None
    vessel_mmsi: str | None
    status: str | None
    event_type: str
    detail: str | None
    source_url: str | None
    observed_at: datetime


async def fetch_source_text(url: str) -> str:
    headers = {"User-Agent": settings.source_http_user_agent}
    async with httpx.AsyncClient(timeout=settings.source_http_timeout_seconds, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        logger.info(
            "source_fetch_complete",
            url=url,
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
            content_length=len(response.text),
        )
        if settings.source_fetch_debug:
            logger.info(
                "source_fetch_preview",
                url=url,
                preview=_preview_text(response.text),
            )
        return response.text


def parse_carrier_schedule_payload(payload_text: str, *, carrier: str, source_url: str | None = None) -> list[ParsedCarrierSchedule]:
    rows = _coerce_rows(payload_text)
    parsed: list[ParsedCarrierSchedule] = []
    scraped_at = datetime.now(timezone.utc)
    for row in rows:
        vessel_name = _pick(row, "vessel", "vessel_name", "ship", "ship_name")
        vessel_imo = _pick(row, "imo", "vessel_imo")
        port_value = _pick(row, "port", "destination", "discharge_port", "port_locode", "terminal")
        port_locode = _to_port_locode(port_value)
        eta = _parse_datetime(_pick(row, "eta", "arrival", "arrival_time", "eta_date"))
        etd = _parse_datetime(_pick(row, "etd", "departure", "departure_time", "etd_date"))
        if not port_locode or not (vessel_name or vessel_imo) or not (eta or etd):
            continue
        parsed.append(
            ParsedCarrierSchedule(
                carrier=carrier,
                voyage_code=_pick(row, "voyage", "voyage_code", "service", "rotation"),
                vessel_name=sanitize_text(vessel_name) if vessel_name else None,
                vessel_imo=sanitize_text(vessel_imo) if vessel_imo else None,
                port_locode=port_locode,
                etd=etd,
                eta=eta,
                source_url=sanitize_url(source_url) if source_url else None,
                scraped_at=scraped_at,
            )
        )
    if not parsed:
        if carrier == "sallaum":
            parsed = _parse_sallaum_schedule_text(payload_text, source_url=source_url)
        elif carrier == "grimaldi":
            parsed = _parse_grimaldi_schedule_text(payload_text, source_url=source_url)
    logger.info(
        "carrier_schedule_parsed",
        carrier=carrier,
        parsed_rows=len(parsed),
        raw_row_count=len(rows),
    )
    if settings.source_fetch_debug and rows:
        logger.info("carrier_schedule_first_row", carrier=carrier, row=rows[0])
    return parsed


def parse_port_observation_payload(payload_text: str, *, source_url: str | None = None) -> list[ParsedPortObservation]:
    rows = _coerce_rows(payload_text)
    parsed: list[ParsedPortObservation] = []
    for row in rows:
        port_locode = _to_port_locode(_pick(row, "port", "port_name", "location")) or _to_terminal_locode(_pick(row, "terminal", "terminal_name"))
        observed_at = _parse_extended_datetime(_pick(row, "observed_at", "time", "updated_at", "timestamp", "expected_time_eta"))
        vessel_name = _pick(row, "vessel", "vessel_name", "ship", "ship_name")
        vessel_imo = _pick(row, "imo", "vessel_imo", "imo_number")
        vessel_mmsi = _pick(row, "mmsi", "vessel_mmsi")
        status = _pick(row, "status", "state")
        event_type = _infer_port_event_type(status, _pick(row, "event_type"), row=row)
        if not port_locode or not observed_at or not (vessel_name or vessel_imo or vessel_mmsi):
            continue
        detail = _pick(row, "detail", "remarks", "note", "comment")
        parsed.append(
            ParsedPortObservation(
                port_locode=port_locode,
                terminal_name=_pick(row, "terminal", "terminal_name"),
                vessel_name=sanitize_text(vessel_name) if vessel_name else None,
                vessel_imo=sanitize_text(vessel_imo) if vessel_imo else None,
                vessel_mmsi=sanitize_text(vessel_mmsi) if vessel_mmsi else None,
                status=sanitize_text(status) if status else None,
                event_type=event_type,
                detail=sanitize_text(detail) if detail else None,
                source_url=sanitize_url(source_url) if source_url else None,
                observed_at=observed_at,
            )
        )
    logger.info(
        "port_observation_parsed",
        parsed_rows=len(parsed),
        raw_row_count=len(rows),
    )
    if settings.source_fetch_debug and rows:
        logger.info("port_observation_first_row", row=rows[0])
    return parsed


async def persist_carrier_schedules(
    session: AsyncSession,
    *,
    source_name: str,
    schedules: list[ParsedCarrierSchedule],
) -> dict[str, int]:
    shipments = await _load_shipments(session)
    counters = {"schedules": 0, "revisions": 0, "evidence": 0, "matched_rows": 0, "unmatched_rows": 0}
    for item in schedules:
        session.add(
            CarrierSchedule(
                carrier=item.carrier,
                voyage_code=item.voyage_code,
                vessel_name=item.vessel_name,
                vessel_imo=item.vessel_imo,
                port_locode=item.port_locode,
                etd=item.etd,
                eta=item.eta,
                source=source_name,
                source_url=item.source_url,
                scraped_at=item.scraped_at,
            )
        )
        counters["schedules"] += 1

        if not item.port_locode:
            logger.info("carrier_schedule_row_skipped", source=source_name, reason="missing_port", vessel_name=item.vessel_name, vessel_imo=item.vessel_imo)
            counters["unmatched_rows"] += 1
            continue
        if not item.vessel_name and not item.vessel_imo:
            logger.info("carrier_schedule_row_skipped", source=source_name, reason="missing_vessel_identity", port_locode=item.port_locode)
            counters["unmatched_rows"] += 1
            continue

        matched = _match_schedule_shipments(shipments, item)
        logger.info(
            "carrier_schedule_match_result",
            source=source_name,
            vessel_name=item.vessel_name,
            vessel_imo=item.vessel_imo,
            port_locode=item.port_locode,
            matched_shipments=[shipment.id for shipment in matched],
        )
        if matched:
            counters["matched_rows"] += 1
        else:
            counters["unmatched_rows"] += 1
        for shipment in matched:
            if item.eta is not None:
                changed = await _record_eta_revision_if_changed(
                    session,
                    shipment=shipment,
                    new_eta=item.eta,
                    source=source_name,
                )
                if changed:
                    counters["revisions"] += 1
            claim = _build_schedule_claim(item)
            if await _ensure_evidence(session, shipment_id=shipment.id, source=source_name, claim=claim, captured_at=item.scraped_at):
                counters["evidence"] += 1
    await session.flush()
    logger.info("carrier_schedule_persist_summary", source=source_name, **counters)
    return counters


async def persist_port_observations(
    session: AsyncSession,
    *,
    source_name: str,
    observations: list[ParsedPortObservation],
) -> dict[str, int]:
    shipments = await _load_shipments(session)
    counters = {"observations": 0, "events": 0, "evidence": 0, "matched_rows": 0, "unmatched_rows": 0}
    for item in observations:
        if await _port_observation_exists(session, item):
            continue
        session.add(
            PortObservation(
                port_locode=item.port_locode,
                terminal_name=item.terminal_name,
                vessel_name=item.vessel_name,
                vessel_imo=item.vessel_imo,
                vessel_mmsi=item.vessel_mmsi,
                status=item.status,
                event_type=item.event_type,
                detail=item.detail,
                source=source_name,
                source_url=item.source_url,
                observed_at=item.observed_at,
            )
        )
        counters["observations"] += 1

        if not item.port_locode:
            logger.info("port_observation_row_skipped", source=source_name, reason="missing_port", vessel_name=item.vessel_name, vessel_imo=item.vessel_imo, vessel_mmsi=item.vessel_mmsi)
            counters["unmatched_rows"] += 1
            continue
        if not item.vessel_name and not item.vessel_imo and not item.vessel_mmsi:
            logger.info("port_observation_row_skipped", source=source_name, reason="missing_vessel_identity", port_locode=item.port_locode)
            counters["unmatched_rows"] += 1
            continue

        matched = _match_port_shipments(shipments, item)
        logger.info(
            "port_observation_match_result",
            source=source_name,
            vessel_name=item.vessel_name,
            vessel_imo=item.vessel_imo,
            vessel_mmsi=item.vessel_mmsi,
            port_locode=item.port_locode,
            matched_shipments=[shipment.id for shipment in matched],
        )
        if matched:
            counters["matched_rows"] += 1
        else:
            counters["unmatched_rows"] += 1
        for shipment in matched:
            if await _ensure_voyage_event(
                session,
                shipment_id=shipment.id,
                vessel_imo=item.vessel_imo,
                event_type=item.event_type,
                event_at=item.observed_at,
                details=_build_port_event_detail(item),
                source=source_name,
            ):
                counters["events"] += 1
            if await _ensure_evidence(
                session,
                shipment_id=shipment.id,
                source=source_name,
                claim=_build_port_claim(item),
                captured_at=item.observed_at,
            ):
                counters["evidence"] += 1
    await session.flush()
    logger.info("port_observation_persist_summary", source=source_name, **counters)
    return counters


def _coerce_rows(payload_text: str) -> list[dict[str, str]]:
    stripped = payload_text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        data = json.loads(stripped)
        if isinstance(data, list):
            return [_normalize_row_dict(item) for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("rows", "items", "data", "results"):
                value = data.get(key)
                if isinstance(value, list):
                    return [_normalize_row_dict(item) for item in value if isinstance(item, dict)]
        return []
    return _parse_html_table_rows(payload_text)


def _parse_html_table_rows(html: str) -> list[dict[str, str]]:
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, flags=re.IGNORECASE | re.DOTALL)
    for table in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, flags=re.IGNORECASE | re.DOTALL)
        if len(rows) < 2:
            continue
        headers = _extract_cells(rows[0])
        if not headers:
            continue
        normalized_headers = [_normalize_key(cell) for cell in headers]
        parsed_rows: list[dict[str, str]] = []
        for raw_row in rows[1:]:
            cells = _extract_cells(raw_row)
            if len(cells) != len(normalized_headers):
                continue
            parsed_rows.append({key: value for key, value in zip(normalized_headers, cells)})
        if parsed_rows:
            return parsed_rows
    return []


def _extract_cells(row_html: str) -> list[str]:
    cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row_html, flags=re.IGNORECASE | re.DOTALL)
    return [_clean_html_text(cell) for cell in cells]


def _clean_html_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    collapsed = re.sub(r"\s+", " ", unescape(without_tags)).strip()
    return collapsed


def _normalize_row_dict(row: dict[str, Any]) -> dict[str, str]:
    return {_normalize_key(str(key)): str(value).strip() for key, value in row.items() if value is not None}


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _pick(row: dict[str, str], *keys: str) -> str | None:
    normalized = {_normalize_key(key) for key in keys}
    for key, value in row.items():
        if key in normalized and value:
            return value
    return None


def _to_port_locode(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    for alias, locode in PORT_LOCODE_ALIASES.items():
        if alias in lowered:
            return locode
    upper = value.strip().upper()
    if re.fullmatch(r"[A-Z]{5,10}", upper):
        return upper
    return None


def _to_terminal_locode(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    for alias, locode in TERMINAL_PORT_ALIASES.items():
        if alias in lowered:
            return locode
    return None


def _infer_port_event_type(status: str | None, explicit: str | None, row: dict[str, str] | None = None) -> str:
    if explicit:
        return _normalize_key(explicit)
    normalized = _normalize_key(status or "")
    if not normalized and row and _pick(row, "expected_time_eta"):
        return "expected_arrival"
    if "anchor" in normalized:
        return "arrived_anchorage"
    if "berth" in normalized or "moored" in normalized:
        return "vessel_berthed"
    if "depart" in normalized or "sailed" in normalized:
        return "departed_port"
    return "port_status_observed"


async def _load_shipments(session: AsyncSession) -> list[Shipment]:
    result = await session.execute(
        select(Shipment).options(
            selectinload(Shipment.candidate_vessels).selectinload(ShipmentVessel.vessel),
            selectinload(Shipment.evidence_items),
        )
    )
    return list(result.scalars().all())


def _match_schedule_shipments(shipments: list[Shipment], item: ParsedCarrierSchedule) -> list[Shipment]:
    matched: list[Shipment] = []
    for shipment in shipments:
        if shipment.carrier.lower() != item.carrier.lower():
            _log_schedule_no_match(shipment, item, reason="carrier_mismatch")
            continue
        if shipment.discharge_port and shipment.discharge_port != item.port_locode:
            _log_schedule_no_match(shipment, item, reason="port_mismatch")
            continue
        shipment_matched = False
        for candidate in shipment.candidate_vessels:
            vessel = candidate.vessel
            if item.vessel_imo and vessel.imo and vessel.imo == item.vessel_imo:
                matched.append(shipment)
                shipment_matched = True
                break
            if item.vessel_name and _normalized_name(vessel.name) == _normalized_name(item.vessel_name):
                matched.append(shipment)
                shipment_matched = True
                break
        if not shipment_matched:
            _log_schedule_no_match(shipment, item, reason="candidate_vessel_mismatch")
    return matched


def _match_port_shipments(shipments: list[Shipment], item: ParsedPortObservation) -> list[Shipment]:
    matched: list[Shipment] = []
    for shipment in shipments:
        shipment_matched = False
        for candidate in shipment.candidate_vessels:
            vessel = candidate.vessel
            if item.vessel_imo and vessel.imo and vessel.imo == item.vessel_imo:
                matched.append(shipment)
                shipment_matched = True
                break
            if item.vessel_mmsi and vessel.mmsi and vessel.mmsi == item.vessel_mmsi:
                matched.append(shipment)
                shipment_matched = True
                break
            if item.vessel_name and _normalized_name(vessel.name) == _normalized_name(item.vessel_name):
                matched.append(shipment)
                shipment_matched = True
                break
        if not shipment_matched:
            _log_port_no_match(shipment, item, reason="candidate_vessel_mismatch")
    return matched


def _normalized_name(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]+", "", (value or "").upper())


async def _record_eta_revision_if_changed(
    session: AsyncSession,
    *,
    shipment: Shipment,
    new_eta: datetime,
    source: str,
) -> bool:
    previous_eta = shipment.declared_eta_date
    latest_result = await session.execute(
        select(ETARevisionLog)
        .where(ETARevisionLog.shipment_id == shipment.id)
        .order_by(ETARevisionLog.revision_at.desc())
        .limit(1)
    )
    latest = latest_result.scalar_one_or_none()
    if latest and latest.new_eta is not None:
        previous_eta = latest.new_eta
    if previous_eta is not None and abs((new_eta - previous_eta).total_seconds()) < 60:
        return False

    delta_hours = None
    if previous_eta is not None:
        delta_hours = round((new_eta - previous_eta).total_seconds() / 3600, 2)
    session.add(
        ETARevisionLog(
            shipment_id=shipment.id,
            carrier=shipment.carrier,
            revision_at=datetime.now(timezone.utc),
            previous_eta=previous_eta,
            new_eta=new_eta,
            delta_hours=delta_hours,
            source=source,
        )
    )
    shipment.declared_eta_date = new_eta
    return True


async def _ensure_evidence(
    session: AsyncSession,
    *,
    shipment_id: str,
    source: str,
    claim: str,
    captured_at: datetime,
) -> bool:
    result = await session.execute(
        select(Evidence.id)
        .where(Evidence.shipment_id == shipment_id)
        .where(Evidence.source == source)
        .where(Evidence.claim == claim)
        .limit(1)
    )
    if result.scalar_one_or_none():
        return False
    session.add(
        Evidence(
            shipment_id=shipment_id,
            source=source,
            captured_at=captured_at,
            claim=claim,
        )
    )
    return True


async def _ensure_voyage_event(
    session: AsyncSession,
    *,
    shipment_id: str,
    vessel_imo: str | None,
    event_type: str,
    event_at: datetime,
    details: str,
    source: str,
) -> bool:
    result = await session.execute(
        select(VoyageEvent.id)
        .where(VoyageEvent.shipment_id == shipment_id)
        .where(VoyageEvent.event_type == event_type)
        .where(VoyageEvent.event_at == event_at)
        .where(VoyageEvent.source == source)
        .limit(1)
    )
    if result.scalar_one_or_none():
        return False
    session.add(
        VoyageEvent(
            shipment_id=shipment_id,
            vessel_imo=vessel_imo,
            event_type=event_type,
            event_at=event_at,
            details=details,
            source=source,
        )
    )
    return True


async def _port_observation_exists(session: AsyncSession, item: ParsedPortObservation) -> bool:
    result = await session.execute(
        select(PortObservation.id)
        .where(PortObservation.port_locode == item.port_locode)
        .where(PortObservation.observed_at == item.observed_at)
        .where(PortObservation.vessel_name == item.vessel_name)
        .where(PortObservation.status == item.status)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def _build_schedule_claim(item: ParsedCarrierSchedule) -> str:
    eta_text = item.eta.isoformat() if item.eta else "unknown ETA"
    vessel = item.vessel_name or item.vessel_imo or "unspecified vessel"
    return f"Carrier schedule shows {vessel} with ETA {eta_text} for {item.port_locode}."


def _build_port_claim(item: ParsedPortObservation) -> str:
    vessel = item.vessel_name or item.vessel_imo or item.vessel_mmsi or "tracked vessel"
    status = item.status or item.event_type.replace("_", " ")
    return f"Nigerian ports feed reported {vessel} as {status} at {item.port_locode}."


def _build_port_event_detail(item: ParsedPortObservation) -> str:
    base = _build_port_claim(item)
    if item.detail:
        return f"{base} {item.detail}"
    return base


def _preview_text(value: str, limit: int = 500) -> str:
    collapsed = re.sub(r"\s+", " ", value).strip()
    return collapsed[:limit]


def _log_schedule_no_match(shipment: Shipment, item: ParsedCarrierSchedule, *, reason: str) -> None:
    logger.info(
        "carrier_schedule_match_miss",
        reason=reason,
        shipment_id=shipment.id,
        shipment_carrier=shipment.carrier,
        shipment_discharge_port=shipment.discharge_port,
        candidate_vessels=[candidate.vessel.name for candidate in shipment.candidate_vessels],
        schedule_vessel_name=item.vessel_name,
        schedule_vessel_imo=item.vessel_imo,
        schedule_port_locode=item.port_locode,
    )


def _log_port_no_match(shipment: Shipment, item: ParsedPortObservation, *, reason: str) -> None:
    logger.info(
        "port_observation_match_miss",
        reason=reason,
        shipment_id=shipment.id,
        shipment_carrier=shipment.carrier,
        shipment_discharge_port=shipment.discharge_port,
        candidate_vessels=[candidate.vessel.name for candidate in shipment.candidate_vessels],
        observed_vessel_name=item.vessel_name,
        observed_vessel_imo=item.vessel_imo,
        observed_vessel_mmsi=item.vessel_mmsi,
        observed_port_locode=item.port_locode,
    )


def _parse_extended_datetime(value: str | None) -> datetime | None:
    parsed = _parse_datetime(value)
    if parsed is not None or not value:
        return parsed
    cleaned = value.replace("Thu,", "").replace("Fri,", "").replace("Sat,", "").replace("Sun,", "").replace("Mon,", "").replace("Tue,", "").replace("Wed,", "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    # Handle odd strings like "March 26, 2026 13:03 PM"
    match = re.match(r"([A-Za-z]+ \d{1,2}, \d{4}) (\d{1,2}:\d{2}) ([AP]M)", cleaned)
    if match:
        date_part, time_part, suffix = match.groups()
        hour, minute = map(int, time_part.split(":"))
        if suffix == "PM" and hour < 12:
            hour += 12
        if suffix == "AM" and hour == 12:
            hour = 0
        try:
            dt = datetime.strptime(f"{date_part} {hour:02d}:{minute:02d}", "%B %d, %Y %H:%M")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _parse_sallaum_schedule_text(payload_text: str, *, source_url: str | None = None) -> list[ParsedCarrierSchedule]:
    lines = [_clean_html_text(line) for line in payload_text.splitlines()]
    lines = [line for line in lines if line]
    flattened = " ".join(lines)
    vessel_names = re.findall(r"(Grand Pioneer|Rcc Classic|Lake Wanaka|Glovis Sonic|Glovis Solomon|Ocean Breeze|Ocean Explorer)", flattened, flags=re.IGNORECASE)
    voyage_codes = re.findall(r"\b\d{2}[A-Z]{2}\d{2}\b", flattened)
    lagos_dates = re.findall(r"Lagos\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})", flattened, flags=re.IGNORECASE)
    if not vessel_names or not voyage_codes:
        return []
    parsed: list[ParsedCarrierSchedule] = []
    scraped_at = datetime.now(timezone.utc)
    for index, vessel_name in enumerate(vessel_names):
        eta = None
        if index < len(lagos_dates):
            eta = _parse_extended_datetime(f"{lagos_dates[index]} 00:00 AM")
        parsed.append(
            ParsedCarrierSchedule(
                carrier="sallaum",
                voyage_code=voyage_codes[index] if index < len(voyage_codes) else None,
                vessel_name=sanitize_text(vessel_name),
                vessel_imo=None,
                port_locode="NGLOS",
                etd=None,
                eta=eta,
                source_url=sanitize_url(source_url) if source_url else None,
                scraped_at=scraped_at,
            )
        )
    return parsed


def _parse_grimaldi_schedule_text(payload_text: str, *, source_url: str | None = None) -> list[ParsedCarrierSchedule]:
    lines = [_clean_html_text(line) for line in payload_text.splitlines()]
    lines = [line for line in lines if line]
    parsed: list[ParsedCarrierSchedule] = []
    scraped_at = datetime.now(timezone.utc)
    current_vessels: list[tuple[str, str | None]] = []
    seen_lagos = False
    for line in lines:
        if "Service" in line and "West Africa" in line:
            current_vessels = []
            seen_lagos = False
            continue
        if re.search(r"Grande|Great", line):
            names = re.findall(r"(Grande [A-Za-z]+|Great [A-Za-z]+)", line)
            if names:
                current_vessels = [(sanitize_text(name), None) for name in names]
                continue
        if current_vessels and re.search(r"\b[A-Z]{3}\d{4}\b", line):
            codes = re.findall(r"\b[A-Z]{3}\d{4}\b", line)
            current_vessels = [
                (name, codes[idx] if idx < len(codes) else None)
                for idx, (name, _) in enumerate(current_vessels)
            ]
            continue
        if current_vessels and line.startswith("Lagos"):
            dates = re.findall(r"\d{1,2}/\d{2}", line)
            for idx, (name, code) in enumerate(current_vessels):
                eta = None
                date_index = idx * 2
                if date_index < len(dates):
                    eta = _parse_grimaldi_short_date(dates[date_index])
                parsed.append(
                    ParsedCarrierSchedule(
                        carrier="grimaldi",
                        voyage_code=code,
                        vessel_name=name,
                        vessel_imo=None,
                        port_locode="NGLOS",
                        etd=None,
                        eta=eta,
                        source_url=sanitize_url(source_url) if source_url else None,
                        scraped_at=scraped_at,
                    )
                )
            seen_lagos = True
        if seen_lagos and parsed:
            break
    return parsed


def _parse_grimaldi_short_date(value: str) -> datetime | None:
    try:
        day, month = value.split("/")
        dt = datetime(year=2026, month=int(month), day=int(day), tzinfo=timezone.utc)
        return dt
    except Exception:
        return None
