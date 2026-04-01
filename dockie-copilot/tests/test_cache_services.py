from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.application.services import ShipmentService, SourceHealthService
from app.infrastructure.cache import CacheLockLease


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, object] = {}

    async def get_json(self, key: str):
        return self.store.get(key)

    async def set_json(self, key: str, value, ttl_seconds: int) -> None:
        del ttl_seconds
        self.store[key] = value

    async def delete_by_prefix(self, prefix: str) -> None:
        for key in list(self.store):
            if key.startswith(prefix):
                del self.store[key]

    async def ping(self) -> bool:
        return True


class FakeCacheCoordinator:
    def __init__(self) -> None:
        self.acquired_keys: list[str] = []
        self.waited_keys: list[str] = []
        self._leases: dict[str, CacheLockLease] = {}

    async def try_acquire(self, key: str, lease_seconds: int) -> CacheLockLease:
        del lease_seconds
        lease = CacheLockLease(key=key, token="token", acquired=True)
        self.acquired_keys.append(key)
        self._leases[key] = lease
        return lease

    async def release(self, lease: CacheLockLease) -> None:
        self._leases.pop(lease.key, None)

    async def wait_for_json(self, cache_key: str, *, timeout_ms: int, poll_interval_ms: int):
        del timeout_ms, poll_interval_ms
        self.waited_keys.append(cache_key)
        return None


@pytest.mark.anyio
async def test_list_shipments_uses_cache_after_first_read():
    cache = FakeCache()
    service = ShipmentService(session=None, cache=cache)  # type: ignore[arg-type]

    calls = {"count": 0}

    async def fake_get_all_summary():
        calls["count"] += 1
        return [
            SimpleNamespace(
                id="ship-001",
                booking_ref="SAL-LAG-24001",
                carrier="sallaum",
                service_lane="US -> West Africa",
                load_port="USBAL",
                discharge_port="NGLOS",
                cargo_type="ro-ro",
                units=42,
                status="open",
                declared_departure_date=None,
                declared_eta_date=None,
                candidate_vessels=[],
            )
        ]

    service._shipment_repo.get_all_summary = fake_get_all_summary  # type: ignore[method-assign]

    first = await service.list_shipments()
    second = await service.list_shipments()

    assert calls["count"] == 1
    assert first[0].id == "ship-001"
    assert second[0].id == "ship-001"


@pytest.mark.anyio
async def test_source_health_uses_cache_after_first_read():
    cache = FakeCache()
    service = SourceHealthService(session=None, cache=cache)  # type: ignore[arg-type]

    calls = {"count": 0}

    async def fake_get_all():
        calls["count"] += 1
        return [
            SimpleNamespace(
                source="aisstream",
                source_class="public_api_terms",
                automation_safety="moderate",
                business_safe_default=True,
                source_status="healthy",
                last_success_at=None,
                stale_after_seconds=3600,
                degraded_reason=None,
                updated_at=None,
            )
        ]

    service._repo.get_all = fake_get_all  # type: ignore[method-assign]

    first = await service.list_health()
    second = await service.list_health()

    assert calls["count"] == 1
    assert first[0].source == "aisstream"
    assert second[0].source == "aisstream"


@pytest.mark.anyio
async def test_get_shipment_status_uses_db_ranked_latest_position_query():
    cache = FakeCache()
    coordinator = FakeCacheCoordinator()
    executed = {"count": 0}

    class FakeResult:
        def __init__(self, value) -> None:
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class FakeSession:
        async def execute(self, statement):
            del statement
            executed["count"] += 1
            return FakeResult(secondary_position)

    service = ShipmentService(session=FakeSession(), cache=cache, cache_coordinator=coordinator)  # type: ignore[arg-type]

    shipment = SimpleNamespace(
        id="ship-001",
        booking_ref="SAL-LAG-24001",
        carrier="sallaum",
        status="open",
        declared_eta_date=datetime.now(timezone.utc) + timedelta(days=7),
        evidence_items=[object()],
        candidate_vessels=[
            SimpleNamespace(
                vessel_id="vessel-a",
                is_primary=True,
                vessel=SimpleNamespace(
                    imo="IMO-A",
                    mmsi="MMSI-A",
                    name="Primary Vessel",
                ),
            ),
            SimpleNamespace(
                vessel_id="vessel-b",
                is_primary=False,
                vessel=SimpleNamespace(
                    imo="IMO-B",
                    mmsi="MMSI-B",
                    name="Secondary Vessel",
                ),
            ),
        ],
    )

    now = datetime.now(timezone.utc)
    primary_position = SimpleNamespace(
        id="pos-a",
        mmsi="MMSI-A",
        imo="IMO-A",
        vessel_name="Primary Vessel",
        latitude=5.1,
        longitude=3.4,
        sog_knots=12.0,
        cog_degrees=85.0,
        heading_degrees=84.0,
        navigation_status="under_way",
        destination_text="NGLOS",
        source="aisstream",
        observed_at=now - timedelta(minutes=15),
    )
    secondary_position = SimpleNamespace(
        id="pos-b",
        mmsi="MMSI-B",
        imo="IMO-B",
        vessel_name="Secondary Vessel",
        latitude=5.2,
        longitude=3.5,
        sog_knots=11.0,
        cog_degrees=80.0,
        heading_degrees=79.0,
        navigation_status="under_way",
        destination_text="NGLOS",
        source="aisstream",
        observed_at=now - timedelta(minutes=5),
    )

    async def fake_get_by_id(shipment_id: str):
        assert shipment_id == "ship-001"
        return shipment

    async def fail_point_lookup(_identifier: str):
        raise AssertionError("point lookup should not be used")

    service._shipment_repo.get_by_id = fake_get_by_id  # type: ignore[method-assign]
    service._position_repo.get_latest_for_mmsi = fail_point_lookup  # type: ignore[method-assign]
    service._position_repo.get_latest_for_imo = fail_point_lookup  # type: ignore[method-assign]

    result = await service.get_shipment_status("ship-001")

    assert result is not None
    assert result.shipment_id == "ship-001"
    assert result.latest_position is not None
    assert result.latest_position.mmsi == "MMSI-B"
    assert executed["count"] == 1
    assert coordinator.acquired_keys == ["lock:shipments:status:ship-001"]


@pytest.mark.anyio
async def test_get_shipment_status_waits_for_shared_cache_fill_before_recomputing():
    cache = FakeCache()

    class WaitingCoordinator:
        async def try_acquire(self, key: str, lease_seconds: int) -> CacheLockLease:
            del key, lease_seconds
            return CacheLockLease(key="lock", token="token", acquired=False)

        async def release(self, lease: CacheLockLease) -> None:
            del lease

        async def wait_for_json(self, cache_key: str, *, timeout_ms: int, poll_interval_ms: int):
            del timeout_ms, poll_interval_ms
            await asyncio.sleep(0)
            return cache.store[cache_key]

    service = ShipmentService(
        session=None,
        cache=cache,
        cache_coordinator=WaitingCoordinator(),  # type: ignore[arg-type]
    )
    cache.store["shipments:status:ship-002"] = {
        "shipment_id": "ship-002",
        "booking_ref": "SAL-LAG-24002",
        "carrier": "sallaum",
        "status": "open",
        "declared_eta": None,
        "latest_position": None,
        "eta_confidence": {
            "confidence": 0.2,
            "freshness": "unknown",
            "explanation": "No position data available. ETA is from carrier declaration only.",
            "declared_eta": None,
        },
        "candidate_vessels": [],
        "evidence_count": 0,
        "freshness_warning": "No position data available. ETA is from carrier declaration only.",
    }

    async def fail_get_by_id(_shipment_id: str):
        raise AssertionError("shipment lookup should not run when another worker filled the cache")

    service._shipment_repo.get_by_id = fail_get_by_id  # type: ignore[method-assign]

    result = await service.get_shipment_status("ship-002")

    assert result is not None
    assert result.shipment_id == "ship-002"
