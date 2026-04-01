#!/usr/bin/env bash
set -euo pipefail

CAPTURE_PATH="${CAPTURE_PATH:-runtime/aisstream/diagnostic_capture.json}"
SHIPMENTS_PATH="${SHIPMENTS_PATH:-runtime/aisstream/manual_shipments.json}"
SELECTED_CAPTURE_PATH="${SELECTED_CAPTURE_PATH:-runtime/aisstream/selected_capture.json}"

./01_aisdiag_capture.sh "$CAPTURE_PATH"
./02_create_manual_shipments.sh "$CAPTURE_PATH" "$SHIPMENTS_PATH"
./03_ingest_selected_capture.sh "$CAPTURE_PATH" "$SHIPMENTS_PATH" "$SELECTED_CAPTURE_PATH"

echo
echo "Check source health:"
curl -sS http://localhost:8000/source-health
echo
echo
echo "Check shipments:"
curl -sS http://localhost:8000/shipments
echo
