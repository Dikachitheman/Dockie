from __future__ import annotations

from app.infrastructure.source_feeds import (
    parse_carrier_schedule_payload,
    parse_port_observation_payload,
)


def test_parse_carrier_schedule_payload_from_html_table():
    html = """
    <table>
      <tr><th>Vessel</th><th>IMO</th><th>Port</th><th>ETA</th><th>Voyage</th></tr>
      <tr><td>Great Abidjan</td><td>9935040</td><td>Lagos</td><td>2026-04-05T00:00:00Z</td><td>WAF-19</td></tr>
    </table>
    """

    rows = parse_carrier_schedule_payload(html, carrier="sallaum", source_url="https://example.test")

    assert len(rows) == 1
    row = rows[0]
    assert row.carrier == "sallaum"
    assert row.vessel_name == "Great Abidjan"
    assert row.vessel_imo == "9935040"
    assert row.port_locode == "NGLOS"
    assert row.voyage_code == "WAF-19"
    assert row.eta is not None


def test_parse_port_observation_payload_from_json():
    payload = """
    [
      {
        "port": "Tin Can",
        "terminal": "Tin Can Island Terminal",
        "vessel_name": "Great Abidjan",
        "imo": "9935040",
        "status": "berthed",
        "observed_at": "2026-04-06T09:30:00Z",
        "detail": "Berth A"
      }
    ]
    """

    rows = parse_port_observation_payload(payload, source_url="https://example.test")

    assert len(rows) == 1
    row = rows[0]
    assert row.port_locode == "NGTIN"
    assert row.event_type == "vessel_berthed"
    assert row.vessel_name == "Great Abidjan"
    assert row.vessel_imo == "9935040"
    assert row.observed_at.isoformat() == "2026-04-06T09:30:00+00:00"


def test_parse_port_observation_payload_supports_nigerian_ports_shape():
    payload = """
    [
      {
        "ship": "ALS FIDES",
        "imo_number": "9938315",
        "terminal": "APM Terminal Ltd",
        "expected_time_eta": "Thu, March 26, 2026 13:03 PM",
        "cargo": "CONTAINER"
      }
    ]
    """

    rows = parse_port_observation_payload(payload, source_url="https://shippos.nigerianports.gov.ng/")

    assert len(rows) == 1
    row = rows[0]
    assert row.port_locode == "NGAPP"
    assert row.vessel_name == "ALS FIDES"
    assert row.vessel_imo == "9938315"
    assert row.event_type == "expected_arrival"


def test_parse_carrier_schedule_payload_supports_sallaum_matrix_fallback():
    payload = """
    <html>
      <body>
        Grand Pioneer 26GP01
        RCC Classic 26RL01
        Lagos 12 April 2026
        Lagos 20 April 2026
      </body>
    </html>
    """

    rows = parse_carrier_schedule_payload(payload, carrier="sallaum", source_url="https://example.test")

    assert rows
    assert rows[0].carrier == "sallaum"
    assert rows[0].port_locode == "NGLOS"
