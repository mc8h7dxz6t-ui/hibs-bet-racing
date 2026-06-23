"""NeMo / creative approval header parsing."""

from __future__ import annotations

from ad_guard.creative import parse_creative_approved


def test_nemo_approved_header():
    assert parse_creative_approved({"X-Nemo-Approved": "true"}) is True


def test_bedrock_guard_passed():
    assert parse_creative_approved({"X-Bedrock-Guard-Passed": "yes"}) is True


def test_creative_denied():
    assert parse_creative_approved({"X-Nemo-Safety-Passed": "false"}) is False


def test_no_header_returns_none():
    assert parse_creative_approved({}) is None
