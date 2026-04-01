#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"
CAPTURE_PATH="${1:-runtime/aisstream/diagnostic_capture.json}"
OUT_PATH="${2:-runtime/aisstream/manual_shipments.json}"
SHIPMENT_COUNT="${SHIPMENT_COUNT:-5}"

if ! curl -fsS "$API_BASE/health" >/dev/null 2>&1; then
  echo "Backend is not reachable at $API_BASE. Start the API first." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT_PATH")"

python - <<'PY' "$CAPTURE_PATH" "$OUT_PATH" "$SHIPMENT_COUNT" "$API_BASE"
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

capture_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])
shipment_count = int(sys.argv[3])
api_base = sys.argv[4].rstrip("/")

payload = json.loads(capture_path.read_text(encoding="utf-8"))
sample = payload.get("sample") or []
selected = sample[:shipment_count]

results = {
    "capture_path": str(capture_path),
    "api_base": api_base,
    "selected_count": len(selected),
    "created": [],
    "skipped": [],
}

for item in selected:
    mmsi = str(item.get("mmsi") or "")
    vessel_name = str(item.get("vessel_name") or "").strip()
    if not mmsi or not vessel_name:
        results["skipped"].append({"reason": "missing_mmsi_or_name", "item": item})
        continue

    body = {
        "shipment_label": f"AIS Live Demo {vessel_name} {mmsi[-6:]}",
        "vessel_name": vessel_name,
        "mmsi": mmsi,
        "imo": item.get("imo") or None,
        "carrier": "manual_tracking",
        "service_lane": "Manual live tracking",
        "discharge_port": item.get("destination_text") or None,
        "cargo_type": "tracked vessel",
        "units": 1,
    }
    request = urllib.request.Request(
        f"{api_base}/shipments/manual",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            created = json.loads(response.read().decode("utf-8"))
            results["created"].append(
                {
                    "shipment_id": created["id"],
                    "booking_ref": created["booking_ref"],
                    "mmsi": mmsi,
                    "vessel_name": vessel_name,
                }
            )
            print(f"Created {created['id']} for {vessel_name} ({mmsi})")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        results["skipped"].append(
            {
                "mmsi": mmsi,
                "vessel_name": vessel_name,
                "status_code": exc.code,
                "detail": detail,
            }
        )
        print(f"Skipped {vessel_name} ({mmsi}) with HTTP {exc.code}")

out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"Saved shipment creation results to {out_path}")
PY
