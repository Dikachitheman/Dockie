from __future__ import annotations

from pathlib import Path

import pytest

from app.infrastructure import sources
from app.infrastructure.aisstream import AISCaptureResult


def test_fixture_connector_reports_overlay_mode():
    connector = sources.FixtureResourcePackConnector()

    readiness = connector.readiness()

    assert readiness.source == "fixtures"
    assert readiness.mode == "overlay"
    assert readiness.business_safe_default is True


def test_fixture_connector_prefers_refresh_pack(monkeypatch, tmp_path):
    baseline = tmp_path / "baseline.json"
    refresh = tmp_path / "refresh.json"
    baseline.write_text("{}", encoding="utf-8")
    refresh.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(sources.settings, "resource_pack_path", str(baseline))
    monkeypatch.setattr(sources.settings, "resource_pack_refresh_path", str(refresh))

    connector = sources.FixtureResourcePackConnector()

    readiness = connector.readiness()

    assert readiness.configured is True
    assert Path(sources.settings.resource_pack_refresh_path).name in readiness.detail


def test_fixture_connector_falls_back_to_baseline_when_refresh_pack_missing(monkeypatch, tmp_path):
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(sources.settings, "resource_pack_path", str(baseline))
    monkeypatch.setattr(sources.settings, "resource_pack_refresh_path", str(tmp_path / "missing.json"))

    connector = sources.FixtureResourcePackConnector()

    readiness = connector.readiness()

    assert readiness.configured is True
    assert Path(sources.settings.resource_pack_path).name in readiness.detail


def test_build_source_connectors_includes_fixture_and_live_overlays():
    connectors = sources.build_source_connectors()
    names = [connector.source_name for connector in connectors]

    assert names[0] == "fixtures"
    assert "aisstream" in names
    assert "sallaum" in names
    assert "grimaldi" in names
    assert "nigerian_ports" in names


def test_source_readiness_exposes_overlay_mode_for_aisstream():
    readiness = {
        item.source: item
        for item in sources.list_source_readiness()
    }

    assert readiness["aisstream"].mode == "overlay"
    assert readiness["aisstream"].detail
    if readiness["aisstream"].configured:
        assert "capture" in readiness["aisstream"].detail.lower()
    else:
        assert "AISSTREAM_API_KEY" in readiness["aisstream"].detail


@pytest.mark.asyncio
async def test_aisstream_refresh_returns_idle_when_no_tracked_mmsis(monkeypatch):
    connector = sources.AISStreamLiveConnector()
    monkeypatch.setattr(sources.settings, "aisstream_api_key", "test-key")

    async def fake_load(_session):
        return []

    monkeypatch.setattr(sources, "_load_tracked_mmsis", fake_load)

    result = await connector.refresh(session=None)  # type: ignore[arg-type]

    assert result.status == "idle"
    assert "No shipment-linked MMSIs" in result.detail


@pytest.mark.asyncio
async def test_aisstream_refresh_uses_live_capture_and_ingest(monkeypatch):
    connector = sources.AISStreamLiveConnector()
    monkeypatch.setattr(sources.settings, "aisstream_api_key", "test-key")

    async def fake_load(_session):
        return ["357123000"]

    async def fake_capture(*, api_key: str, mmsis: list[str]):
        assert api_key
        assert mmsis == ["357123000"]
        return AISCaptureResult(
            positions=[
                {
                    "mmsi": "357123000",
                    "imo": "9935040",
                    "vessel_name": "GREAT ABIDJAN",
                    "latitude": 5.25,
                    "longitude": 3.85,
                    "sog_knots": 14.2,
                    "cog_degrees": 92.5,
                    "heading_degrees": 93,
                    "navigation_status": "under_way_using_engine",
                    "destination_text": "LAGOS",
                    "observed_at": "2026-03-20T12:00:00+00:00",
                    "source": "aisstream",
                }
            ],
            inspected_messages=14,
            matched_positions=1,
            requested_mmsis=1,
        )

    def fake_save_snapshot(path, capture):
        assert capture.matched_positions == 1
        return "runtime/aisstream/latest_capture.json"

    async def fake_ingest(_session, path, commit=False):
        assert commit is False
        assert str(path).endswith("latest_capture.json")
        return {"positions": 1, "quarantined": 0, "skipped_stale": 0}

    monkeypatch.setattr(sources, "_load_tracked_mmsis", fake_load)
    monkeypatch.setattr(sources, "capture_positions_for_mmsis", fake_capture)
    monkeypatch.setattr(sources, "save_capture_snapshot", fake_save_snapshot)
    monkeypatch.setattr(sources, "ingest_position_snapshot_file", fake_ingest)

    result = await connector.refresh(session=object())  # type: ignore[arg-type]

    assert result.status == "healthy"
    assert result.records_ingested == 1
    assert "Captured 1 live AIS positions" in result.detail
    assert "Snapshot saved to runtime/aisstream/latest_capture.json" in result.detail


@pytest.mark.asyncio
async def test_carrier_schedule_connector_reports_not_configured_without_url():
    connector = sources.CarrierScheduleConnector(source_name="sallaum", enabled=True, url=None)

    result = await connector.refresh(session=None)  # type: ignore[arg-type]

    assert result.status == "not_configured"


@pytest.mark.asyncio
async def test_carrier_schedule_connector_ingests_rows(monkeypatch):
    connector = sources.CarrierScheduleConnector(
        source_name="grimaldi",
        enabled=True,
        url="https://example.test/grimaldi",
    )

    async def fake_fetch(_url: str):
        return "<table><tr><th>Vessel</th><th>Port</th><th>ETA</th></tr><tr><td>Great Tema</td><td>Apapa</td><td>2026-04-03T00:00:00Z</td></tr></table>"

    def fake_parse(payload: str, *, carrier: str, source_url: str | None = None):
        assert "Great Tema" in payload
        assert carrier == "grimaldi"
        return [object()]

    async def fake_persist(_session, *, source_name: str, schedules: list[object]):
        assert source_name == "grimaldi"
        assert len(schedules) == 1
        return {"schedules": 1, "revisions": 1, "evidence": 1}

    monkeypatch.setattr(sources, "fetch_source_text", fake_fetch)
    monkeypatch.setattr(sources, "parse_carrier_schedule_payload", fake_parse)
    monkeypatch.setattr(sources, "persist_carrier_schedules", fake_persist)

    result = await connector.refresh(session=object())  # type: ignore[arg-type]

    assert result.status == "healthy"
    assert result.records_ingested == 1
    assert "ETA revisions" in result.detail


@pytest.mark.asyncio
async def test_nigerian_ports_connector_ingests_rows(monkeypatch):
    connector = sources.NigerianPortsConnector()
    monkeypatch.setattr(sources.settings, "nigerian_ports_url", "https://example.test/ports")

    async def fake_fetch(_url: str):
        return '{"rows": [{"port":"Tin Can","vessel_name":"Great Abidjan","status":"berthed","observed_at":"2026-04-06T09:30:00Z"}]}'

    def fake_parse(payload: str, *, source_url: str | None = None):
        assert "berthed" in payload
        return [object()]

    async def fake_persist(_session, *, source_name: str, observations: list[object]):
        assert source_name == "nigerian_ports"
        assert len(observations) == 1
        return {"observations": 1, "events": 1, "evidence": 1}

    monkeypatch.setattr(sources, "fetch_source_text", fake_fetch)
    monkeypatch.setattr(sources, "parse_port_observation_payload", fake_parse)
    monkeypatch.setattr(sources, "persist_port_observations", fake_persist)

    result = await connector.refresh(session=object())  # type: ignore[arg-type]

    assert result.status == "healthy"
    assert result.records_ingested == 1
    assert "voyage events" in result.detail
