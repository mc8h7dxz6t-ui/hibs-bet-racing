"""Insights page context — lightweight path (no full group_meetings)."""

from __future__ import annotations

import pandas as pd

from hibs_racing.web_service import (
    insights_context,
    meeting_days_from_card_dates,
    race_deep_link_index,
    resolve_race_deep_link,
)


def test_race_deep_link_index_resolves_race_id():
    frame = pd.DataFrame(
        [
            {"card_date": "2026-07-14", "course": "Ascot", "race_id": "r1", "off_time": "14:30"},
            {"card_date": "2026-07-14", "course": "Ascot", "race_id": "r1", "off_time": "14:30"},
            {"card_date": "2026-07-14", "course": "Ascot", "race_id": "r2", "off_time": "15:00"},
        ]
    )
    index = race_deep_link_index(frame)
    link = resolve_race_deep_link(index, race_id="r2")
    assert link["race_id"] == "r2"
    assert link["meeting"]
    assert link["race"].startswith("race-")


def test_meeting_days_from_card_dates_labels():
    days = meeting_days_from_card_dates(["2026-07-15", "2026-07-14"])
    assert [d["card_date"] for d in days] == ["2026-07-14", "2026-07-15"]
    assert days[0]["meetings"] == []


def test_insights_context_skips_heavy_group_meetings(monkeypatch):
    frame = pd.DataFrame(
        [
            {
                "card_date": "2026-07-14",
                "race_id": "r1",
                "runner_id": "r1:a",
                "horse_name": "Alpha",
                "field_size": 8,
                "model_place_prob": 0.55,
                "combo_bayes_place": 0.4,
                "off_time": "14:00",
                "course": "Ascot",
            }
        ]
    )

    monkeypatch.setattr("hibs_racing.web_service._base_frame", lambda **_: frame)
    monkeypatch.setattr("hibs_racing.web_service.group_meetings", lambda _frame: [])
    monkeypatch.setattr(
        "hibs_racing.daily.pick_display.build_value_lane_display_picks",
        lambda meetings, f, **_: [],
    )
    monkeypatch.setattr(
        "hibs_racing.models.feature_impact.load_feature_impact_report",
        lambda: {},
    )
    monkeypatch.setattr(
        "hibs_racing.web_service._ui_data_status",
        lambda _frame: {"level": "ok", "messages": []},
    )
    monkeypatch.setattr(
        "hibs_racing.web_service.health_status",
        lambda: type(
            "H",
            (),
            {
                "value_lane_ready": True,
                "value_lane_blockers": [],
                "to_dict": lambda self: {"value_lane_ready": True},
            },
        )(),
    )

    ctx = insights_context(top_n=5)
    assert "top_picks" in ctx
    assert "picks_by_day" in ctx
    assert "value_lane_picks" in ctx
    assert ctx["value_lane_picks"] == []
    assert "pick_candidates" not in ctx
