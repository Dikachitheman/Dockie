"""
Source policy definitions.

Each source is classified with explicit metadata so the system can
make automated decisions about trust, freshness, and degradation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SourcePolicy:
    name: str
    source_class: str
    automation_safety: str
    business_safe_default: bool
    role: str
    health_expectation: str
    fallback_behavior: str
    stale_after_seconds: int


SOURCE_POLICIES: dict[str, SourcePolicy] = {
    "aisstream": SourcePolicy(
        name="aisstream",
        source_class="public_api_terms",
        automation_safety="moderate",
        business_safe_default=True,
        role="live movement bootstrap",
        health_expectation="best-effort, occasionally degraded",
        fallback_behavior="keep last known position and lower freshness confidence",
        stale_after_seconds=3600,
    ),
    "grimaldi": SourcePolicy(
        name="grimaldi",
        source_class="public_api_terms",
        automation_safety="fragile_scraper",
        business_safe_default=True,
        role="carrier schedule and fleet context",
        health_expectation="parser break risk",
        fallback_behavior="retain last trusted schedule snapshot and mark route claims stale",
        stale_after_seconds=604800,
    ),
    "sallaum": SourcePolicy(
        name="sallaum",
        source_class="public_api_terms",
        automation_safety="fragile_scraper",
        business_safe_default=True,
        role="route intent and schedule",
        health_expectation="parser break risk",
        fallback_behavior="retain last trusted schedule snapshot and mark route claims stale",
        stale_after_seconds=604800,
    ),
    "orbcomm": SourcePolicy(
        name="orbcomm",
        source_class="noncommercial_or_license_limited",
        automation_safety="moderate",
        business_safe_default=False,
        role="supplementary vessel positions",
        health_expectation="rate-limited, license constraints apply",
        fallback_behavior="do not use as sole position source; surface caveat",
        stale_after_seconds=7200,
    ),
    "global_fishing_watch": SourcePolicy(
        name="global_fishing_watch",
        source_class="public_api_terms",
        automation_safety="moderate",
        business_safe_default=True,
        role="historical AIS track enrichment",
        health_expectation="delayed data, batch updates",
        fallback_behavior="surface data age clearly",
        stale_after_seconds=86400,
    ),
    "official_sanctions": SourcePolicy(
        name="official_sanctions",
        source_class="open_data",
        automation_safety="high",
        business_safe_default=True,
        role="compliance and watchlist enrichment",
        health_expectation="scheduled official updates",
        fallback_behavior="show last refresh date and coverage gap clearly",
        stale_after_seconds=86400,
    ),
    "nigerian_ports": SourcePolicy(
        name="nigerian_ports",
        source_class="analyst_reference_only",
        automation_safety="validation_required",
        business_safe_default=False,
        role="arrival and berth corroboration",
        health_expectation="useful but structurally fragile",
        fallback_behavior="require analyst confirmation until reliability is proven",
        stale_after_seconds=86400,
    ),
    "carrier_schedule": SourcePolicy(
        name="carrier_schedule",
        source_class="public_api_terms",
        automation_safety="fragile_scraper",
        business_safe_default=True,
        role="declared voyage schedule",
        health_expectation="parser break risk",
        fallback_behavior="retain last trusted schedule and mark stale",
        stale_after_seconds=604800,
    ),
    "historical_ais": SourcePolicy(
        name="historical_ais",
        source_class="open_data",
        automation_safety="high",
        business_safe_default=True,
        role="historical track backfill",
        health_expectation="stable archive",
        fallback_behavior="use as-is, surface data age",
        stale_after_seconds=604800,
    ),
    "untrusted_manual_import": SourcePolicy(
        name="untrusted_manual_import",
        source_class="analyst_reference_only",
        automation_safety="human_in_loop",
        business_safe_default=False,
        role="manual or unverified import",
        health_expectation="always treat as hostile until reviewed",
        fallback_behavior="quarantine and surface for analyst review",
        stale_after_seconds=0,
    ),
}


def get_policy(source: str) -> Optional[SourcePolicy]:
    return SOURCE_POLICIES.get(source)


def get_policy_or_default(source: str) -> SourcePolicy:
    return SOURCE_POLICIES.get(source) or SourcePolicy(
        name=source,
        source_class="analyst_reference_only",
        automation_safety="validation_required",
        business_safe_default=False,
        role="unknown",
        health_expectation="unknown",
        fallback_behavior="quarantine until classified",
        stale_after_seconds=3600,
    )
