"""
Tests for source policy classification and operational rules.
"""

from __future__ import annotations

import pytest

from app.infrastructure.source_policy import (
    SOURCE_POLICIES,
    get_policy,
    get_policy_or_default,
)


class TestSourcePolicy:
    def test_aisstream_is_public_api_terms(self):
        p = get_policy("aisstream")
        assert p is not None
        assert p.source_class == "public_api_terms"
        assert p.business_safe_default is True

    def test_orbcomm_not_business_safe_default(self):
        p = get_policy("orbcomm")
        assert p is not None
        assert p.business_safe_default is False
        assert p.source_class == "noncommercial_or_license_limited"

    def test_nigerian_ports_analyst_only(self):
        p = get_policy("nigerian_ports")
        assert p is not None
        assert p.source_class == "analyst_reference_only"
        assert p.automation_safety == "validation_required"

    def test_official_sanctions_high_automation(self):
        p = get_policy("official_sanctions")
        assert p is not None
        assert p.automation_safety == "high"
        assert p.source_class == "open_data"

    def test_untrusted_manual_import_human_in_loop(self):
        p = get_policy("untrusted_manual_import")
        assert p is not None
        assert p.automation_safety == "human_in_loop"
        assert p.business_safe_default is False
        assert p.stale_after_seconds == 0

    def test_unknown_source_returns_default(self):
        p = get_policy_or_default("some_unknown_source_xyz")
        assert p is not None
        assert p.business_safe_default is False
        assert p.automation_safety == "validation_required"

    def test_unknown_source_get_policy_returns_none(self):
        assert get_policy("nonexistent_source_abc") is None

    def test_all_policies_have_required_fields(self):
        required_fields = [
            "name", "source_class", "automation_safety",
            "business_safe_default", "role", "fallback_behavior",
            "stale_after_seconds",
        ]
        for source, policy in SOURCE_POLICIES.items():
            for field in required_fields:
                assert hasattr(policy, field), f"{source} missing field {field}"

    def test_fragile_scrapers_have_fallback(self):
        scrapers = [
            s for s, p in SOURCE_POLICIES.items()
            if p.automation_safety == "fragile_scraper"
        ]
        assert len(scrapers) > 0
        for s in scrapers:
            p = SOURCE_POLICIES[s]
            assert p.fallback_behavior, f"{s} missing fallback_behavior"
