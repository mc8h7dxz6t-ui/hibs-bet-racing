"""Dashboard / insights performance guards."""

from __future__ import annotations

import pandas as pd

from hibs_racing.web_service import _cap_dashboard_frame


def test_cap_dashboard_frame_limits_large_multi_day_frame():
    rows = []
    for day in range(10):
        card_date = f"2026-08-{day + 1:02d}"
        for n in range(200):
            rows.append(
                {
                    "card_date": card_date,
                    "runner_id": f"{card_date}:{n}",
                    "race_id": f"{card_date}:r{n % 8}",
                    "off_time": "14:30",
                    "course": "Ascot",
                }
            )
    frame = pd.DataFrame(rows)
    out = _cap_dashboard_frame(frame, max_runners=500)
    assert len(out) <= 500
    assert out["card_date"].astype(str).str[:10].nunique() <= 3
