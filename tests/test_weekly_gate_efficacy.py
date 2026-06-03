from hibs_racing.institutional.weekly_gate_efficacy import format_weekly_markdown


def test_format_weekly_markdown_includes_lanes():
    payload = {
        "ok": True,
        "week_ended": "2026-06-07",
        "start": "2026-06-01",
        "end": "2026-06-07",
        "card_days": 5,
        "runners": 100,
        "config_hash": "abc123",
        "lanes": {
            "Raw Value (No Gates)": {
                "sp": {"settled": 10, "hit_rate": 0.25, "roi_pct": -4.8, "avg_slippage_bps": -14.1},
                "executed": {"settled": 10, "roi_pct": -6.2, "avg_slippage_bps": -14.1},
            },
            "Production Lane": {
                "sp": {"settled": 5, "hit_rate": 0.36, "roi_pct": 48.1, "avg_slippage_bps": -6.8},
                "executed": {"settled": 5, "roi_pct": 41.3, "avg_slippage_bps": -6.8},
            },
        },
    }
    md = format_weekly_markdown(payload)
    assert "Production Lane" in md
    assert "Executed ROI %" in md
    assert "48.1" in md
