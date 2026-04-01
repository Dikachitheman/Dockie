from __future__ import annotations

from app.infrastructure.aisstream import normalize_aisstream_payload


def test_diagnostic_normalization_keeps_identifying_fields():
    payload = {
        "MetaData": {
            "MMSI": 636018145,
            "ShipName": "ACTIVE DEMO",
            "latitude": 6.43,
            "longitude": 3.39,
            "time_utc": "2026-03-29T00:10:00Z",
            "destination": "LAGOS",
        },
        "Message": {
            "PositionReport": {
                "Sog": 10.4,
                "Cog": 120.1,
                "TrueHeading": 121,
                "NavigationalStatus": 1,
            }
        },
    }

    normalized = normalize_aisstream_payload(payload)

    assert normalized is not None
    assert normalized["mmsi"] == "636018145"
    assert normalized["vessel_name"] == "ACTIVE DEMO"
    assert normalized["destination_text"] == "LAGOS"
    assert normalized["navigation_status"] == "at_anchor"
