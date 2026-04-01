from __future__ import annotations

import json

from app.infrastructure.aisstream import AISCaptureResult, save_capture_snapshot


def test_save_capture_snapshot_writes_positions_and_metadata(tmp_path):
    snapshot = tmp_path / "runtime" / "aisstream" / "latest_capture.json"
    capture = AISCaptureResult(
        positions=[
            {
                "mmsi": "601182000",
                "vessel_name": "FUCHSIA",
                "latitude": -33.90659,
                "longitude": 18.42601,
                "observed_at": "2026-03-28T23:21:56+00:00",
                "source": "aisstream",
            }
        ],
        inspected_messages=10,
        matched_positions=1,
        requested_mmsis=1,
        error="no close frame received or sent",
    )

    path = save_capture_snapshot(snapshot, capture)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path == snapshot
    assert payload["inspected_messages"] == 10
    assert payload["matched_positions"] == 1
    assert payload["error"] == "no close frame received or sent"
    assert payload["positions"][0]["mmsi"] == "601182000"
