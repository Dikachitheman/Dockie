#!/usr/bin/env bash
set -euo pipefail

CAPTURE_PATH="${1:-runtime/aisstream/diagnostic_capture.json}"
SHIPMENTS_PATH="${2:-runtime/aisstream/manual_shipments.json}"
OUT_PATH="${3:-runtime/aisstream/selected_capture.json}"

mkdir -p "$(dirname "$OUT_PATH")"

python - <<'PY' "$CAPTURE_PATH" "$SHIPMENTS_PATH" "$OUT_PATH"
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.infrastructure.cache import invalidate_cache_prefix
from app.infrastructure.database import AsyncSessionFactory
from app.infrastructure.ingest import ingest_position_snapshot_file
from app.infrastructure.repositories import SourceHealthRepository

capture_path = Path(sys.argv[1])
shipments_path = Path(sys.argv[2])
out_path = Path(sys.argv[3])

capture = json.loads(capture_path.read_text(encoding="utf-8"))
shipments = json.loads(shipments_path.read_text(encoding="utf-8"))

selected_mmsis = {
    str(item["mmsi"])
    for item in shipments.get("created", [])
    if item.get("mmsi")
}
positions = [
    item
    for item in (capture.get("sample") or [])
    if str(item.get("mmsi") or "") in selected_mmsis
]

snapshot = {
    "captured_at": capture.get("captured_at"),
    "inspected_messages": capture.get("inspected_messages", 0),
    "matched_positions": len(positions),
    "requested_mmsis": len(selected_mmsis),
    "error": None,
    "positions": positions,
}
out_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


async def main() -> None:
    settings = get_settings()
    async with AsyncSessionFactory() as session:
        counters = await ingest_position_snapshot_file(session, out_path, commit=False)
        repo = SourceHealthRepository(session)
        health = await repo.get_by_source("aisstream")
        if health:
            health.source_status = "healthy" if counters["positions"] > 0 else "degraded"
            health.last_success_at = datetime.now(timezone.utc) if counters["positions"] > 0 else health.last_success_at
            health.degraded_reason = None if counters["positions"] > 0 else (
                f"No captured positions matched created shipments from {out_path}."
            )
        await session.commit()

    await invalidate_cache_prefix("shipments:")
    await invalidate_cache_prefix("sources:")
    print(f"Saved selected capture snapshot to {out_path}")
    print(f"Ingested positions: {len(positions)}")


asyncio.run(main())
PY
