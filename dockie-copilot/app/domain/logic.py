"""
Domain logic — pure functions.

No I/O, no DB, no HTTP.
All functions take domain objects and return domain objects or scalars.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from app.domain.models import (
    ETAConfidence,
    FreshnessLevel,
    Position,
    VoyageEvent,
)


# ---------------------------------------------------------------------------
# Freshness
# ---------------------------------------------------------------------------

def compute_freshness(
    observed_at: datetime,
    stale_after_seconds: int,
    *,
    now: Optional[datetime] = None,
) -> FreshnessLevel:
    """Classify a position/signal as fresh, aging, stale, or unknown."""
    if now is None:
        now = datetime.now(timezone.utc)

    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)

    age_seconds = (now - observed_at).total_seconds()

    if age_seconds < 0:
        # Future timestamp — treat as fresh (within acceptable clock skew / pre-dated AIS)
        return FreshnessLevel.FRESH

    half = stale_after_seconds / 2
    if age_seconds <= half:
        return FreshnessLevel.FRESH
    elif age_seconds <= stale_after_seconds:
        return FreshnessLevel.AGING
    else:
        return FreshnessLevel.STALE


def is_stale(
    observed_at: datetime,
    stale_after_seconds: int,
    *,
    now: Optional[datetime] = None,
) -> bool:
    return compute_freshness(observed_at, stale_after_seconds, now=now) == FreshnessLevel.STALE


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

def get_latest_position(positions: Sequence[Position]) -> Optional[Position]:
    """Return the most recent position by observed_at."""
    if not positions:
        return None
    return max(positions, key=lambda p: p.observed_at)


def is_newer_than(candidate: Position, existing: Position) -> bool:
    """True if candidate is strictly more recent than existing."""
    cand_ts = candidate.observed_at
    exist_ts = existing.observed_at
    if cand_ts.tzinfo is None:
        cand_ts = cand_ts.replace(tzinfo=timezone.utc)
    if exist_ts.tzinfo is None:
        exist_ts = exist_ts.replace(tzinfo=timezone.utc)
    return cand_ts > exist_ts


# ---------------------------------------------------------------------------
# ETA confidence
# ---------------------------------------------------------------------------

def compute_eta_confidence(
    declared_eta: Optional[datetime],
    latest_position: Optional[Position],
    stale_after_seconds: int,
    *,
    now: Optional[datetime] = None,
) -> ETAConfidence:
    """
    Produce an ETA confidence assessment combining declared ETA
    and position freshness.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if declared_eta is None and latest_position is None:
        return ETAConfidence(
            confidence=0.0,
            freshness=FreshnessLevel.UNKNOWN,
            explanation="No ETA declared and no position data available.",
        )

    if latest_position is None:
        return ETAConfidence(
            confidence=0.2,
            freshness=FreshnessLevel.UNKNOWN,
            explanation="ETA is from carrier declaration only; no position data to corroborate.",
            declared_eta=declared_eta,
        )

    freshness = compute_freshness(latest_position.observed_at, stale_after_seconds, now=now)

    freshness_factor = {
        FreshnessLevel.FRESH: 1.0,
        FreshnessLevel.AGING: 0.7,
        FreshnessLevel.STALE: 0.3,
        FreshnessLevel.UNKNOWN: 0.1,
    }[freshness]

    base_confidence = 0.5 if declared_eta else 0.3
    confidence = round(base_confidence * freshness_factor, 2)

    explanation_parts = []
    if declared_eta:
        explanation_parts.append(f"Carrier declared ETA {declared_eta.date().isoformat()}.")
    explanation_parts.append(
        f"Latest position is {freshness.value} "
        f"(observed {latest_position.observed_at.isoformat()})."
    )
    if freshness == FreshnessLevel.STALE:
        explanation_parts.append("Position data is stale; ETA reliability is reduced.")

    return ETAConfidence(
        confidence=confidence,
        freshness=freshness,
        explanation=" ".join(explanation_parts),
        declared_eta=declared_eta,
    )


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

def detect_changes_since(
    events: Sequence[VoyageEvent],
    since: datetime,
) -> list[VoyageEvent]:
    """Return events that occurred after `since`."""
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    result = []
    for ev in events:
        ev_at = ev.event_at
        if ev_at.tzinfo is None:
            ev_at = ev_at.replace(tzinfo=timezone.utc)
        if ev_at > since:
            result.append(ev)
    return sorted(result, key=lambda e: e.event_at)
