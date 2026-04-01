from __future__ import annotations

from app.infrastructure.aisstream import normalize_aisstream_payload


def test_normalize_aisstream_payload_maps_position_report_fields():
    payload = {
        "MetaData": {
            "MMSI": 357123000,
            "ShipName": "GREAT ABIDJAN",
            "latitude": 5.25,
            "longitude": 3.85,
            "time_utc": "2026-03-20T12:00:00Z",
            "destination": "LAGOS",
        },
        "Message": {
            "PositionReport": {
                "Cog": 92.5,
                "Sog": 14.2,
                "TrueHeading": 93,
                "NavigationalStatus": 0,
            }
        },
    }

    normalized = normalize_aisstream_payload(payload)

    assert normalized is not None
    assert normalized["mmsi"] == "357123000"
    assert normalized["vessel_name"] == "GREAT ABIDJAN"
    assert normalized["navigation_status"] == "under_way_using_engine"
    assert normalized["source"] == "aisstream"


def test_normalize_aisstream_payload_returns_none_for_incomplete_messages():
    payload = {
        "MetaData": {
            "MMSI": 357123000,
        },
        "Message": {
            "PositionReport": {
                "Sog": 14.2,
            }
        },
    }

    assert normalize_aisstream_payload(payload) is None


def test_normalize_aisstream_payload_accepts_metadata_alias_and_class_b_report():
    payload = {
        "Metadata": {
            "MMSI": 367000980,
            "Name": "CLASS B DEMO",
            "Latitude": 39.562353333333334,
            "Longitude": 2.6283216666666664,
            "time_utc": "2026-03-29T00:20:00Z",
        },
        "Message": {
            "StandardClassBPositionReport": {
                "UserID": 367000980,
                "Latitude": 39.562353333333334,
                "Longitude": 2.6283216666666664,
                "Sog": 0,
                "Cog": 210.5,
                "TrueHeading": 511,
            }
        },
    }

    normalized = normalize_aisstream_payload(payload)

    assert normalized is not None
    assert normalized["mmsi"] == "367000980"
    assert normalized["vessel_name"] == "CLASS B DEMO"
    assert normalized["heading_degrees"] is None


def test_normalize_aisstream_payload_accepts_aisstream_utc_suffix_timestamp():
    payload = {
        "MetaData": {
            "MMSI": 601182000,
            "ShipName": "FUCHSIA             ",
            "latitude": -33.90659,
            "longitude": 18.42601,
            "time_utc": "2026-03-28 23:21:56.639522695 +0000 UTC",
        },
        "Message": {
            "PositionReport": {
                "UserID": 601182000,
                "Latitude": -33.90659166666667,
                "Longitude": 18.42601,
                "Sog": 0,
                "Cog": 360,
                "TrueHeading": 46,
                "NavigationalStatus": 7,
            }
        },
    }

    normalized = normalize_aisstream_payload(payload)

    assert normalized is not None
    assert normalized["mmsi"] == "601182000"
    assert normalized["observed_at"].startswith("2026-03-28T23:21:56")
