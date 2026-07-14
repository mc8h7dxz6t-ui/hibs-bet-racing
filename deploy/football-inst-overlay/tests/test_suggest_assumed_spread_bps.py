"""Tests for suggest_assumed_spread_bps script."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.suggest_assumed_spread_bps import load_live_spreads, suggest_spread_bps


def test_suggest_spread_from_audit(tmp_path: Path):
    audit = tmp_path / "spread.jsonl"
    audit.write_text(
        "\n".join(
            json.dumps({"live_spread_bps": v})
            for v in [4.0, 5.0, 6.0, 8.0, 12.0, 14.0]
        ),
        encoding="utf-8",
    )
    spreads = load_live_spreads(audit)
    out = suggest_spread_bps(spreads)
    assert out["n_observations"] == 6
    assert out["suggested_assumed_spread_bps"] is not None
    assert out["suggested_assumed_spread_bps"] >= 5.0
