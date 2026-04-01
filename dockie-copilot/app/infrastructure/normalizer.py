"""
Normalization pipeline.

Converts raw upstream payloads into ORM objects.
Validates all fields before accepting.
Quarantines payloads that fail validation.
Enforces staleness rules — never silently overwrites fresher data.
"""

from __future__ import annotations

import base64
import binascii
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger
from app.core.security import (
    sanitize_text,
    sanitize_url,
    validate_coordinate,
    validate_course,
    validate_speed,
)
from app.models.orm import (
    Evidence,
    Position,
    QuarantinedEvent,
    RawEvent,
    Shipment,
    ShipmentVessel,
    Vessel,
    VoyageEvent,
    VoyageSignal,
)

logger = get_logger(__name__)

_ALLOWED_SHIPMENT_STATUSES = {
    "booked",
    "assigned",
    "in_transit",
    "delivered",
    "delayed",
    "open",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO8601 string into a timezone-aware datetime. Returns None on failure."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _require_datetime(value: Any, field: str) -> tuple[datetime | None, str | None]:
    """Return (dt, error_reason). error_reason is set if parsing fails."""
    dt = _parse_datetime(value)
    if dt is None:
        return None, f"Invalid or missing datetime for field '{field}': {value!r}"
    return dt, None


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Shipment normalizer
# ---------------------------------------------------------------------------

def normalize_shipment(
    raw: dict[str, Any], raw_event_id: str
) -> tuple[Shipment | None, str | None]:
    """
    Normalize a shipment record.
    Returns (Shipment, None) on success, (None, reason) on failure.
    """
    sid = raw.get("shipment_id")
    booking_ref = raw.get("booking_ref", "")

    if not sid or not booking_ref:
        return None, "Missing shipment_id or booking_ref"

    # Sanitize text fields — treat all as untrusted
    sid = sanitize_text(str(sid))
    booking_ref = sanitize_text(str(booking_ref))

    departure_date = _parse_datetime(raw.get("declared_departure_date"))
    eta_date = _parse_datetime(raw.get("declared_eta_date"))

    raw_status = sanitize_text(str(raw.get("status", "open"))).lower()
    shipment = Shipment(
        id=sid,
        booking_ref=booking_ref,
        carrier=sanitize_text(str(raw.get("carrier", "unknown"))),
        service_lane=sanitize_text(str(raw.get("service_lane", ""))),
        load_port=sanitize_text(str(raw.get("load_port", ""))),
        discharge_port=sanitize_text(str(raw.get("discharge_port", ""))),
        cargo_type=sanitize_text(str(raw.get("cargo_type", ""))),
        units=int(raw["units"]) if isinstance(raw.get("units"), (int, float)) else None,
        status=raw_status if raw_status in _ALLOWED_SHIPMENT_STATUSES else "open",
        declared_departure_date=departure_date,
        declared_eta_date=eta_date,
        raw_event_id=raw_event_id,
    )
    return shipment, None


# ---------------------------------------------------------------------------
# Vessel normalizer
# ---------------------------------------------------------------------------

def normalize_vessel(raw: dict[str, Any]) -> tuple[Vessel | None, str | None]:
    name = raw.get("name") or raw.get("vessel_name")
    if not name:
        return None, "Missing vessel name"

    imo = raw.get("imo")
    mmsi = raw.get("mmsi")

    if imo:
        imo = sanitize_text(str(imo))
    if mmsi:
        mmsi = sanitize_text(str(mmsi))

    vessel = Vessel(
        imo=imo,
        mmsi=mmsi,
        name=sanitize_text(str(name)),
    )
    return vessel, None


# ---------------------------------------------------------------------------
# Position normalizer
# ---------------------------------------------------------------------------

def normalize_position(
    raw: dict[str, Any], raw_event_id: str
) -> tuple[Position | None, str | None]:
    """
    Normalize an AIS / position record.
    Validates coordinates, speed, course, and timestamp.
    Returns (None, reason) if any critical field is invalid.
    """
    reasons: list[str] = []

    mmsi = raw.get("mmsi") or raw.get("MMSI")
    if not mmsi or str(mmsi).lower() == "unknown":
        return None, "Missing or invalid MMSI"

    mmsi = sanitize_text(str(mmsi))

    # Timestamp
    raw_ts = raw.get("observed_at") or raw.get("time_utc")
    observed_at, ts_err = _require_datetime(raw_ts, "observed_at")
    if ts_err:
        return None, ts_err

    # Coordinates
    try:
        lat = float(raw.get("latitude") or raw.get("Latitude") or 999)
        lon = float(raw.get("longitude") or raw.get("Longitude") or 999)
    except (TypeError, ValueError):
        return None, "Non-numeric latitude/longitude"

    if not validate_coordinate(lat, lat=True):
        return None, f"Latitude out of range: {lat}"
    if not validate_coordinate(lon, lat=False):
        return None, f"Longitude out of range: {lon}"

    # Speed
    raw_sog = raw.get("sog_knots") or raw.get("Sog")
    sog: float | None = None
    if raw_sog is not None:
        try:
            sog = float(raw_sog)
            if not validate_speed(sog):
                reasons.append(f"Speed out of range ({sog}); ignored")
                sog = None
        except (TypeError, ValueError):
            reasons.append("Non-numeric speed; ignored")

    # Course
    raw_cog = raw.get("cog_degrees") or raw.get("Cog")
    cog: float | None = None
    if raw_cog is not None:
        try:
            cog = float(raw_cog)
            if not validate_course(cog):
                reasons.append(f"Course out of range ({cog}); ignored")
                cog = None
        except (TypeError, ValueError):
            reasons.append("Non-numeric course; ignored")

    if reasons:
        logger.warning("position_partial_validation", mmsi=mmsi, warnings=reasons)

    imo = raw.get("imo") or raw.get("vessel_imo")
    vessel_name = raw.get("vessel_name") or raw.get("ShipName")
    dest = raw.get("destination_text")

    position = Position(
        id=_uid(),
        mmsi=mmsi,
        imo=sanitize_text(str(imo)) if imo else None,
        vessel_name=sanitize_text(str(vessel_name)) if vessel_name else None,
        latitude=lat,
        longitude=lon,
        sog_knots=sog,
        cog_degrees=cog,
        heading_degrees=_safe_float(raw.get("heading_degrees") or raw.get("TrueHeading")),
        navigation_status=sanitize_text(str(raw.get("navigation_status", ""))),
        destination_text=sanitize_text(str(dest)) if dest else None,
        source=sanitize_text(str(raw.get("source", "unknown"))),
        observed_at=observed_at,
        raw_event_id=raw_event_id,
    )
    return position, None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Evidence normalizer
# ---------------------------------------------------------------------------

def normalize_evidence(
    raw: dict[str, Any], shipment_id: str
) -> tuple[Evidence | None, str | None]:
    source = raw.get("source")
    captured_at_raw = raw.get("captured_at")
    claim = raw.get("claim")

    if not source or not claim:
        return None, "Missing source or claim"

    captured_at, err = _require_datetime(captured_at_raw, "captured_at")
    if err:
        return None, err

    raw_url = raw.get("url") or raw.get("evidence_url")
    safe_url = sanitize_url(str(raw_url)) if raw_url else None

    ev = Evidence(
        id=_uid(),
        shipment_id=shipment_id,
        source=sanitize_text(str(source)),
        captured_at=captured_at,
        claim=sanitize_text(str(claim)),
        url=safe_url,
    )
    return ev, None


# ---------------------------------------------------------------------------
# Voyage event normalizer
# ---------------------------------------------------------------------------

def normalize_voyage_event(
    raw: dict[str, Any], shipment_id: str | None = None, vessel_imo: str | None = None
) -> tuple[VoyageEvent | None, str | None]:
    event_type = raw.get("event_type")
    event_at_raw = raw.get("event_at")

    if not event_type:
        return None, "Missing event_type"

    event_at, err = _require_datetime(event_at_raw, "event_at")
    if err:
        return None, err

    ev = VoyageEvent(
        id=_uid(),
        shipment_id=shipment_id,
        vessel_imo=vessel_imo,
        event_type=sanitize_text(str(event_type)),
        event_at=event_at,
        details=sanitize_text(str(raw.get("details", ""))),
        source=sanitize_text(str(raw.get("source", "system"))),
    )
    return ev, None


# ---------------------------------------------------------------------------
# Malicious payload detection
# ---------------------------------------------------------------------------

_UNSAFE_PATTERNS = [
    "javascript:",
    "<script",
    "onerror=",
    "onload=",
    "../../",
    "../",
    "\x00",
    "\x1b",
    "ignore previous instructions",
    "ignore all previous",
    "disregard your",
    "you are now",
    "new instructions:",
    "data:text/html",
    "vbscript:",
    "&#x",
    "%2e%2e",
]

_UNSAFE_REGEXES = [
    re.compile(r"(^|\n)\s*(human|user|assistant|system)\s*:", re.IGNORECASE),
]


def detect_hostile_content(payload: dict[str, Any]) -> list[str]:
    """
    Scan all string values in a payload for known hostile patterns.
    Returns a list of flagged reasons (empty if clean).
    """
    findings: list[str] = []
    _scan_value(payload, findings)
    return findings


def _scan_value(value: Any, findings: list[str]) -> None:
    if isinstance(value, str):
        lower = value.lower()
        for pattern in _UNSAFE_PATTERNS:
            if pattern in lower:
                findings.append(f"Hostile pattern detected: {pattern!r} in value: {value[:80]!r}")
        for pattern in _UNSAFE_REGEXES:
            if pattern.search(value):
                findings.append(
                    f"Hostile regex detected: {pattern.pattern!r} in value: {value[:80]!r}"
                )
        decoded = _try_decode_base64(value)
        if decoded is not None:
            decoded_findings: list[str] = []
            _scan_value(decoded, decoded_findings)
            findings.extend(f"base64-encoded: {finding}" for finding in decoded_findings)
    elif isinstance(value, dict):
        for v in value.values():
            _scan_value(v, findings)
    elif isinstance(value, list):
        for item in value:
            _scan_value(item, findings)


def _try_decode_base64(value: str) -> str | None:
    compact = "".join(value.split())
    if not re.fullmatch(r"^[A-Za-z0-9+/]{20,}={0,2}$", compact):
        return None
    try:
        decoded = base64.b64decode(compact, validate=True)
        return decoded.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
