"""
Tests for pure domain logic functions.
No DB, no HTTP — all in-memory.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.logic import (
    compute_eta_confidence,
    compute_freshness,
    detect_changes_since,
    get_latest_position,
    is_newer_than,
    is_stale,
)
from app.domain.models import FreshnessLevel, Position, VoyageEvent


def _pos(observed_at: datetime, mmsi: str = "357123000", source: str = "aisstream") -> Position:
    return Position(
        mmsi=mmsi,
        latitude=5.25,
        longitude=3.85,
        observed_at=observed_at,
        source=source,
    )


def _utc(**kwargs) -> datetime:
    return datetime.now(timezone.utc) + timedelta(**kwargs)


class TestFreshness:
    def test_fresh_position(self):
        obs = _utc(minutes=-10)
        result = compute_freshness(obs, stale_after_seconds=3600)
        assert result == FreshnessLevel.FRESH

    def test_aging_position(self):
        obs = _utc(minutes=-40)
        result = compute_freshness(obs, stale_after_seconds=3600)
        assert result == FreshnessLevel.AGING

    def test_stale_position(self):
        obs = _utc(hours=-2)
        result = compute_freshness(obs, stale_after_seconds=3600)
        assert result == FreshnessLevel.STALE

    def test_future_timestamp_is_fresh(self):
        obs = _utc(hours=+1)
        result = compute_freshness(obs, stale_after_seconds=3600)
        assert result == FreshnessLevel.FRESH

    def test_is_stale_true(self):
        obs = _utc(hours=-5)
        assert is_stale(obs, stale_after_seconds=3600) is True

    def test_is_stale_false(self):
        obs = _utc(minutes=-5)
        assert is_stale(obs, stale_after_seconds=3600) is False

    def test_naive_datetime_treated_as_utc(self):
        naive = datetime.utcnow() - timedelta(hours=5)
        result = compute_freshness(naive, stale_after_seconds=3600)
        assert result == FreshnessLevel.STALE


class TestLatestPosition:
    def test_returns_most_recent(self):
        p1 = _pos(_utc(hours=-2))
        p2 = _pos(_utc(hours=-1))
        p3 = _pos(_utc(hours=-3))
        assert get_latest_position([p1, p2, p3]) is p2

    def test_empty_list_returns_none(self):
        assert get_latest_position([]) is None

    def test_single_item(self):
        p = _pos(_utc(hours=-1))
        assert get_latest_position([p]) is p


class TestIsNewer:
    def test_newer_candidate(self):
        existing = _pos(_utc(hours=-2))
        candidate = _pos(_utc(hours=-1))
        assert is_newer_than(candidate, existing) is True

    def test_older_candidate(self):
        existing = _pos(_utc(hours=-1))
        candidate = _pos(_utc(hours=-2))
        assert is_newer_than(candidate, existing) is False

    def test_same_time_not_newer(self):
        t = _utc(hours=-1)
        assert is_newer_than(_pos(t), _pos(t)) is False


class TestETAConfidence:
    def test_no_data_zero_confidence(self):
        result = compute_eta_confidence(None, None, stale_after_seconds=3600)
        assert result.confidence == 0.0
        assert result.freshness == FreshnessLevel.UNKNOWN

    def test_declared_eta_no_position(self):
        eta = _utc(days=+10)
        result = compute_eta_confidence(eta, None, stale_after_seconds=3600)
        assert result.confidence == 0.2
        assert "carrier declaration" in result.explanation.lower()

    def test_fresh_position_boosts_confidence(self):
        eta = _utc(days=+5)
        pos = _pos(_utc(minutes=-10))
        result = compute_eta_confidence(eta, pos, stale_after_seconds=3600)
        assert result.confidence > 0.3
        assert result.freshness == FreshnessLevel.FRESH

    def test_stale_position_lowers_confidence(self):
        eta = _utc(days=+5)
        pos = _pos(_utc(hours=-10))
        result = compute_eta_confidence(eta, pos, stale_after_seconds=3600)
        assert result.confidence < 0.3
        assert result.freshness == FreshnessLevel.STALE
        assert "stale" in result.explanation.lower()


class TestDetectChanges:
    def _event(self, hours_ago: float, etype: str = "test_event") -> VoyageEvent:
        return VoyageEvent(
            event_type=etype,
            event_at=_utc(hours=-hours_ago),
            details="test",
        )

    def test_returns_only_newer_events(self):
        since = _utc(hours=-2)
        events = [
            self._event(3),   # before since
            self._event(1),   # after since
            self._event(0.5), # after since
        ]
        result = detect_changes_since(events, since)
        assert len(result) == 2

    def test_empty_events(self):
        result = detect_changes_since([], _utc(hours=-1))
        assert result == []

    def test_results_sorted_ascending(self):
        since = _utc(hours=-5)
        events = [self._event(1), self._event(3), self._event(2)]
        result = detect_changes_since(events, since)
        times = [e.event_at for e in result]
        assert times == sorted(times)
