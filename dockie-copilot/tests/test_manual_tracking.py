from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.application.services import ShipmentService


def test_build_manual_booking_ref_compacts_label_and_uses_mmsi_suffix():
    service = ShipmentService(session=None)  # type: ignore[arg-type]

    booking_ref = service._build_manual_booking_ref("Great Abidjan Demo Vessel", "357123000")

    assert booking_ref == "GREAT-ABIDJAN-DEMO-VESSE-123000"


def test_build_live_carrier_booking_ref_is_stable_and_readable():
    service = ShipmentService(session=None)  # type: ignore[arg-type]

    booking_ref = service._build_live_carrier_booking_ref(
        carrier="sallaum",
        vessel_name="Grand Pioneer",
        port_locode="NGLOS",
    )

    assert booking_ref == "LIVE-SALLAUM-GRAND-PIONEER-NGLOS"
    assert service._build_live_carrier_shipment_id(booking_ref).startswith("live-")


def test_select_live_import_rows_dedupes_same_vessel_and_port():
    service = ShipmentService(session=None)  # type: ignore[arg-type]
    now = datetime(2026, 3, 29, tzinfo=timezone.utc)

    rows = [
        SimpleNamespace(carrier="sallaum", vessel_name="Grand Pioneer", vessel_imo=None, port_locode="NGLOS", eta=now),
        SimpleNamespace(carrier="sallaum", vessel_name="Grand Pioneer", vessel_imo=None, port_locode="NGLOS", eta=now.replace(day=30)),
        SimpleNamespace(carrier="sallaum", vessel_name="Ocean Breeze", vessel_imo=None, port_locode="NGLOS", eta=now.replace(day=31)),
    ]

    selected = service._select_live_import_rows(rows, limit=5)

    assert len(selected) == 2
    assert {item.vessel_name for item in selected} == {"Grand Pioneer", "Ocean Breeze"}
