"""Structural rescue golden HTML — Wave 3 alt-data hardening."""

from __future__ import annotations

import json
from pathlib import Path

from altdata.structural_rescue import structural_rescue

GOLDEN = Path(__file__).parent / "golden" / "structural_rescue.json"


def test_structural_rescue_golden_cases():
    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for case in cases:
        got = structural_rescue(case["html"], case["field"])
        if case.get("expected") is None:
            assert got is None, case["name"]
        else:
            assert got == case["expected"], case["name"]
