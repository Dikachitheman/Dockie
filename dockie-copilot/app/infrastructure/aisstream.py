"""
AISStream capture and normalization helpers.

The live connector uses a bounded WebSocket capture round so `refresh`
can pull a best-effort snapshot for tracked vessels without needing a
long-running worker process.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.infrastructure.normalizer import _parse_datetime

settings = get_settings()
WORLD_BOUNDING_BOXES = [[[-90, -180], [90, 180]]]
POSITION_MESSAGE_KEYS = (
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
)

AISSTREAM_NAV_STATUS_MAP = {
    0: "under_way_using_engine",
    1: "at_anchor",
    2: "not_under_command",
    3: "restricted_manoeuvrability",
    4: "constrained_by_draught",
    5: "moored",
    6: "aground",
    7: "engaged_in_fishing",
    8: "under_way_sailing",
    15: "undefined",
}


@dataclass(frozen=True)
class AISCaptureResult:
    positions: list[dict[str, Any]]
    inspected_messages: int
    matched_positions: int
    requested_mmsis: int
    error: str | None = None


@dataclass(frozen=True)
class AISDiagnosticResult:
    inspected_messages: int
    sample: list[dict[str, Any]]
    subscribed_mode: str
    message_types: list[str]
    raw_samples: list[dict[str, Any]]


def normalize_aisstream_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    Convert an AISStream message into the position shape expected by
    `normalize_position`. Returns None when no usable position is present.
    """
    metadata = payload.get("MetaData") or payload.get("Metadata") or {}
    message = payload.get("Message") or {}
    report = _extract_position_report(message)

    mmsi = metadata.get("MMSI") or report.get("UserID")
    latitude = _pick_first(
        metadata.get("latitude"),
        metadata.get("Latitude"),
        report.get("Latitude"),
    )
    longitude = _pick_first(
        metadata.get("longitude"),
        metadata.get("Longitude"),
        report.get("Longitude"),
    )
    observed_at = _pick_first(
        metadata.get("time_utc"),
        metadata.get("timeUTC"),
        report.get("time_utc"),
        report.get("Timestamp"),
    )

    if mmsi is None or latitude is None or longitude is None or observed_at is None:
        return None

    heading = report.get("TrueHeading")
    if isinstance(heading, (int, float)) and heading > 360:
        heading = None

    navigation_status = _normalize_navigation_status(
        _pick_first(
            metadata.get("NavigationalStatus"),
            report.get("NavigationalStatus"),
            metadata.get("navigation_status"),
        )
    )

    destination = _pick_first(
        metadata.get("Destination"),
        metadata.get("destination"),
        report.get("Destination"),
    )
    vessel_name = _pick_first(
        metadata.get("ShipName"),
        metadata.get("Name"),
        metadata.get("ship_name"),
        report.get("ShipName"),
        report.get("Name"),
    )

    normalized = {
        "mmsi": str(mmsi),
        "imo": _optional_str(_pick_first(metadata.get("IMO"), report.get("ImoNumber"))),
        "vessel_name": _optional_str(vessel_name),
        "latitude": latitude,
        "longitude": longitude,
        "sog_knots": _pick_first(report.get("Sog"), metadata.get("Sog")),
        "cog_degrees": _pick_first(report.get("Cog"), metadata.get("Cog")),
        "heading_degrees": heading,
        "navigation_status": navigation_status,
        "destination_text": _optional_str(destination),
        "observed_at": _normalize_timestamp(observed_at),
        "source": "aisstream",
    }
    if normalized["observed_at"] is None:
        return None
    return normalized


async def capture_positions_for_mmsis(
    *,
    api_key: str,
    mmsis: list[str],
) -> AISCaptureResult:
    if not mmsis:
        return AISCaptureResult(
            positions=[],
            inspected_messages=0,
            matched_positions=0,
            requested_mmsis=0,
        )

    try:
        import websockets
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "AISStream capture requires the `websockets` package to be installed."
        ) from exc

    requested = list(dict.fromkeys(mmsis))[: settings.aisstream_max_tracked_mmsis]
    requested_set = set(requested)
    latest_by_mmsi: dict[str, dict[str, Any]] = {}
    inspected_messages = 0

    subscription = {
        "APIKey": api_key,
        "BoundingBoxes": WORLD_BOUNDING_BOXES,
        "FiltersShipMMSI": requested,
        "FilterMessageTypes": ["PositionReport"],
    }

    stream_error: str | None = None
    try:
        async with websockets.connect(
            settings.aisstream_ws_url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
            max_size=2**20,
        ) as websocket:
            await websocket.send(json.dumps(subscription))
            deadline = asyncio.get_running_loop().time() + settings.aisstream_capture_window_seconds

            while (
                asyncio.get_running_loop().time() < deadline
                and inspected_messages < settings.aisstream_max_messages
                and len(latest_by_mmsi) < len(requested_set)
            ):
                timeout_seconds = min(
                    settings.aisstream_message_timeout_seconds,
                    max(deadline - asyncio.get_running_loop().time(), 0.1),
                )
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    break
                except Exception as exc:  # pragma: no cover - depends on live network behavior
                    stream_error = str(exc)
                    break

                inspected_messages += 1
                payload = json.loads(message)
                normalized = normalize_aisstream_payload(payload)
                if not normalized:
                    continue

                mmsi = str(normalized["mmsi"])
                if mmsi not in requested_set:
                    continue

                existing = latest_by_mmsi.get(mmsi)
                if existing is None or _is_newer(normalized["observed_at"], existing["observed_at"]):
                    latest_by_mmsi[mmsi] = normalized
    except Exception as exc:  # pragma: no cover - depends on live network behavior
        stream_error = stream_error or str(exc)

    positions = list(latest_by_mmsi.values())
    return AISCaptureResult(
        positions=positions,
        inspected_messages=inspected_messages,
        matched_positions=len(positions),
        requested_mmsis=len(requested),
        error=stream_error,
    )


async def capture_diagnostic_sample(
    *,
    api_key: str,
    sample_size: int = 10,
    raw_sample_size: int = 5,
) -> AISDiagnosticResult:
    try:
        import websockets
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "AISStream capture requires the `websockets` package to be installed."
        ) from exc

    sample_by_mmsi: dict[str, dict[str, Any]] = {}
    message_types_seen: set[str] = set()
    raw_samples: list[dict[str, Any]] = []
    inspected_messages = 0
    subscription = {
        "APIKey": api_key,
        "BoundingBoxes": WORLD_BOUNDING_BOXES,
        "FilterMessageTypes": ["PositionReport"],
    }

    async with websockets.connect(
        settings.aisstream_ws_url,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=5,
        max_size=2**20,
    ) as websocket:
        await websocket.send(json.dumps(subscription))
        deadline = asyncio.get_running_loop().time() + settings.aisstream_capture_window_seconds

        while (
            asyncio.get_running_loop().time() < deadline
            and inspected_messages < settings.aisstream_max_messages
            and len(sample_by_mmsi) < sample_size
        ):
            timeout_seconds = min(
                settings.aisstream_message_timeout_seconds,
                max(deadline - asyncio.get_running_loop().time(), 0.1),
            )
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                break

            inspected_messages += 1
            payload = json.loads(message)
            message_type = str(payload.get("MessageType") or "unknown")
            message_types_seen.add(message_type)
            if len(raw_samples) < raw_sample_size:
                raw_samples.append(
                    {
                        "message_type": message_type,
                        "keys": sorted(payload.keys()),
                        "metadata_keys": sorted((payload.get("MetaData") or payload.get("Metadata") or {}).keys()),
                        "message_keys": sorted((payload.get("Message") or {}).keys()),
                        "payload": payload,
                    }
                )
            normalized = normalize_aisstream_payload(payload)
            if not normalized:
                continue

            mmsi = str(normalized["mmsi"])
            sample_by_mmsi[mmsi] = {
                "mmsi": mmsi,
                "imo": normalized.get("imo"),
                "vessel_name": normalized.get("vessel_name"),
                "latitude": normalized.get("latitude"),
                "longitude": normalized.get("longitude"),
                "observed_at": normalized.get("observed_at"),
                "source": normalized.get("source"),
                "navigation_status": normalized.get("navigation_status"),
                "destination_text": normalized.get("destination_text"),
            }

    return AISDiagnosticResult(
        inspected_messages=inspected_messages,
        sample=list(sample_by_mmsi.values()),
        subscribed_mode="global_position_report_sample",
        message_types=sorted(message_types_seen),
        raw_samples=raw_samples,
    )


def _pick_first(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _extract_position_report(message: dict[str, Any]) -> dict[str, Any]:
    for key in POSITION_MESSAGE_KEYS:
        report = message.get(key)
        if isinstance(report, dict):
            return report
    if len(message) == 1:
        report = next(iter(message.values()))
        if isinstance(report, dict):
            return report
    return {}


def _normalize_navigation_status(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered.isdigit():
            mapped = AISSTREAM_NAV_STATUS_MAP.get(int(lowered))
            return mapped or lowered
        return lowered.replace(" ", "_")
    if isinstance(value, (int, float)):
        return AISSTREAM_NAV_STATUS_MAP.get(int(value), str(int(value)))
    return str(value)


def _normalize_timestamp(value: Any) -> str | None:
    parsed = _parse_datetime(value)
    if parsed is None and isinstance(value, str):
        cleaned = re.sub(r"\s+UTC$", "", value.strip())
        cleaned = re.sub(r"\.(\d{6})\d+\s", r".\1 ", cleaned)
        cleaned = re.sub(r"\s([+-]\d{2})(\d{2})$", r" \1:\2", cleaned)
        parsed = _parse_datetime(cleaned)
    if parsed is None:
        return None
    return parsed.isoformat()


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _is_newer(left: Any, right: Any) -> bool:
    left_dt = _coerce_datetime(left)
    right_dt = _coerce_datetime(right)
    if left_dt is None or right_dt is None:
        return False
    return left_dt > right_dt


def _coerce_datetime(value: Any) -> datetime | None:
    return _parse_datetime(value)


def save_capture_snapshot(path: str | Path, capture: AISCaptureResult) -> Path:
    snapshot_path = Path(path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(
            {
                "captured_at": datetime.utcnow().isoformat() + "Z",
                "inspected_messages": capture.inspected_messages,
                "matched_positions": capture.matched_positions,
                "requested_mmsis": capture.requested_mmsis,
                "error": capture.error,
                "positions": capture.positions,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return snapshot_path
