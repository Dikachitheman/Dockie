#!/usr/bin/env bash
set -euo pipefail

OUT_PATH="${1:-runtime/aisstream/diagnostic_capture.json}"
SAMPLE_SIZE="${SAMPLE_SIZE:-25}"

mkdir -p "$(dirname "$OUT_PATH")"

python - <<'PY' "$OUT_PATH" "$SAMPLE_SIZE"
import asyncio
import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.infrastructure.aisstream import capture_diagnostic_sample

out_path = Path(sys.argv[1])
sample_size = int(sys.argv[2])


async def main() -> None:
    settings = get_settings()
    if not settings.aisstream_api_key:
        raise SystemExit("AISSTREAM_API_KEY is not configured.")

    result = await capture_diagnostic_sample(
        api_key=settings.aisstream_api_key,
        sample_size=sample_size,
    )
    payload = {
        "captured_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "subscribed_mode": result.subscribed_mode,
        "inspected_messages": result.inspected_messages,
        "message_types": result.message_types,
        "sample_count": len(result.sample),
        "sample": result.sample,
        "raw_samples": result.raw_samples,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved diagnostic capture to {out_path}")
    print(f"Inspected messages: {payload['inspected_messages']}")
    print(f"Unique vessel samples: {payload['sample_count']}")
    if payload["sample"]:
        print("First samples:")
        for item in payload["sample"][:10]:
            print(f"  - {item.get('mmsi')} :: {str(item.get('vessel_name') or '').strip()}")


asyncio.run(main())
PY
