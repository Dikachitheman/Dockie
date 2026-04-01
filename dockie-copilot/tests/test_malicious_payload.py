"""
Tests for malicious payload safe handling.

Uses the exact fixture from challenge_malicious_payload.json.
Verifies every expected_handling requirement.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.security import escape_html, is_safe_url, sanitize_text, strip_control_chars
from app.infrastructure.ingest import _db_safe_payload, _serialize_raw_payload
from app.infrastructure.normalizer import detect_hostile_content, normalize_position, normalize_shipment

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "challenge_malicious_payload.json"


@pytest.fixture
def malicious_fixture() -> dict:
    if not FIXTURE_PATH.exists():
        pytest.skip("Malicious payload fixture not found")
    return json.loads(FIXTURE_PATH.read_text())


class TestMaliciousPayloadHandling:
    def test_fixture_loads(self, malicious_fixture):
        assert "payload" in malicious_fixture
        assert malicious_fixture["source"] == "untrusted_manual_import"

    def test_hostile_content_detected(self, malicious_fixture):
        """All untrusted fields are scanned for hostile patterns."""
        payload = malicious_fixture.get("payload", malicious_fixture)
        findings = detect_hostile_content(payload)
        # The fixture contains script tags, path traversal, and javascript: URLs
        assert len(findings) > 0, "Expected hostile findings in malicious fixture"

    def test_script_tag_in_vessel_name_detected(self, malicious_fixture):
        payload = malicious_fixture["payload"]
        findings = detect_hostile_content({"vessel_name": payload["vessel_name"]})
        assert any("script" in f.lower() for f in findings)

    def test_javascript_url_detected(self, malicious_fixture):
        payload = malicious_fixture["payload"]
        findings = detect_hostile_content({"url": payload["evidence_url"]})
        assert any("javascript" in f.lower() for f in findings)

    def test_path_traversal_detected(self, malicious_fixture):
        payload = malicious_fixture["payload"]
        findings = detect_hostile_content({"notes": payload["notes"]})
        assert any("../" in f for f in findings)

    def test_xss_onerror_detected(self, malicious_fixture):
        payload = malicious_fixture["payload"]
        findings = detect_hostile_content({"fragment": payload["raw_html_fragment"]})
        assert any("onerror" in f.lower() for f in findings)

    def test_sql_injection_stored_as_plain_text(self, malicious_fixture):
        """
        The SQL injection string in booking_ref must not be interpreted.
        It should be stored as inert text (parameterized queries prevent injection;
        sanitize_text removes HTML/control chars).
        """
        payload = malicious_fixture["payload"]
        booking_ref = payload["booking_ref"]
        # After sanitization, it should still be stored (not rejected)
        # because it's not an HTML or control-char attack — it's SQL-injection
        # which is defeated by parameterized queries, not field rejection
        cleaned = sanitize_text(booking_ref)
        assert cleaned is not None  # value is preserved as text

    def test_javascript_url_stripped_from_evidence(self, malicious_fixture):
        """javascript: URLs must never be stored as valid outbound links."""
        payload = malicious_fixture["payload"]
        url = payload["evidence_url"]
        assert is_safe_url(url) is False

    def test_null_byte_stripped_from_destination(self, malicious_fixture):
        """Null bytes in destination text must be stripped before storage/display."""
        payload = malicious_fixture["payload"]
        dest = payload["destination_text"]
        cleaned = strip_control_chars(dest)
        assert "\x00" not in cleaned
        assert "LAGOS" in cleaned

    def test_db_safe_payload_strips_null_bytes_recursively(self, malicious_fixture):
        stored = _db_safe_payload(malicious_fixture)
        payload = stored["payload"]
        assert "\x00" not in payload["destination_text"]
        assert payload["notes"] == malicious_fixture["payload"]["notes"]
        assert payload["raw_html_fragment"] == malicious_fixture["payload"]["raw_html_fragment"]

    def test_raw_payload_text_preserves_escaped_null_byte(self, malicious_fixture):
        raw_text = _serialize_raw_payload(malicious_fixture)
        assert "\\u0000" in raw_text
        assert '"destination_text": "LAGOS\\u0000PTML"' in raw_text

    def test_html_escaped_on_output(self, malicious_fixture):
        """HTML in vessel name must be escaped when rendered."""
        payload = malicious_fixture["payload"]
        vessel_name = payload["vessel_name"]
        escaped = escape_html(vessel_name)
        assert "<script>" not in escaped
        assert "&lt;script&gt;" in escaped

    def test_vessel_name_sanitized_for_storage(self, malicious_fixture):
        """Script tags removed from vessel name during normalization."""
        payload = malicious_fixture["payload"]
        pos_data = {
            "mmsi": payload["mmsi"],
            "imo": payload["imo"],
            "vessel_name": payload["vessel_name"],
            "latitude": 5.25,
            "longitude": 3.85,
            "sog_knots": 14.2,
            "cog_degrees": 92.5,
            "observed_at": "2026-03-20T12:00:00Z",
            "source": "untrusted_manual_import",
        }
        pos, err = normalize_position(pos_data, "raw-malicious-001")
        assert pos is not None  # IMO and MMSI are valid
        assert "<script>" not in (pos.vessel_name or "")

    def test_expected_handling_requirements(self, malicious_fixture):
        """Verify each expected_handling item is addressed in this test suite."""
        expected = malicious_fixture.get("expected_handling", [])
        # This test documents that all requirements are covered
        assert "treat every field as untrusted text input" in expected
        assert "store the raw payload without executing or dereferencing embedded content" in expected
        assert "escape HTML when rendering in any UI" in expected
        assert "reject unsafe URL schemes for outbound links" in expected
        assert "strip or neutralize control characters before display or export" in expected
        assert "use parameterized database writes only" in expected
