"""Tests for engine-suggested racing system bet combinations."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from hibs_racing.entity.timezone import LONDON
from hibs_racing.tips.suggested_combinations import (
    build_engine_combinations,
    build_engine_combinations_by_day,
)


def _pick_row(**overrides):
    base = {
        "race_id": "R1",
        "horse_name": "Alpha",
        "course": "Ascot",
        "off_time": "14:30",
        "card_date": "2026-07-22",
        "runner_id": "run-1",
        "field_size": 8,
        "model_place_prob": 0.5,
        "combo_bayes_place": 0.4,
        "win_decimal": 4.5,
        "value_flag": 1,
        "ew_combined_ev": 0.12,
    }
    base.update(overrides)
    return base


def test_build_engine_combinations_empty_when_few_value_picks():
    frame = pd.DataFrame([_pick_row()])
    out = build_engine_combinations(frame, top_n=6)
    assert out["combinations"] == []
    assert out["pick_count"] == 1
    assert out["pick_source"] == "value_lane"
    assert out["message"]


def test_build_engine_combinations_ignores_non_value_runners():
    frame = pd.DataFrame(
        [
            _pick_row(race_id="R1", horse_name="ValueA", ew_combined_ev=0.2),
            _pick_row(race_id="R2", horse_name="NoValue", value_flag=0, ew_combined_ev=0.99),
        ]
    )
    out = build_engine_combinations(frame, top_n=6)
    assert out["combinations"] == []
    assert out["pick_count"] == 1


def test_build_engine_combinations_builds_value_lane_double_trixie_lucky15():
    frame = pd.DataFrame(
        [
            _pick_row(race_id="R1", horse_name="A", runner_id="r1", ew_combined_ev=0.22, win_decimal=3.0),
            _pick_row(race_id="R2", horse_name="B", runner_id="r2", ew_combined_ev=0.18, win_decimal=4.0),
            _pick_row(race_id="R3", horse_name="C", runner_id="r3", ew_combined_ev=0.15, win_decimal=5.0),
            _pick_row(race_id="R4", horse_name="D", runner_id="r4", ew_combined_ev=0.11, win_decimal=6.0),
            _pick_row(race_id="R5", horse_name="E", runner_id="r5", ew_combined_ev=0.08, win_decimal=7.0),
        ]
    )
    out = build_engine_combinations(frame, top_n=5)
    types = [c["type"] for c in out["combinations"]]
    assert types == ["double", "trixie", "lucky_15"]
    assert out["pick_source"] == "value_lane"
    leg = out["combinations"][0]["legs"][0]
    assert leg["selection"] == "A"
    assert leg["ew_combined_ev"] == 0.22
    assert leg["card_date"] == "2026-07-22"
    assert "Ascot" in leg["event"]
    assert "14:30" in leg["event"]
    assert out["combinations"][0]["pick_source"] == "value_lane"
    assert out["combinations"][-1]["bet_count"] == 15
    assert len(out["singles"]) == 1
    assert out["singles"][0]["selection"] == "E"


def test_build_engine_combinations_by_day_splits_today_and_tomorrow():
    today = datetime.now(LONDON).date().isoformat()
    tomorrow = (datetime.now(LONDON).date() + timedelta(days=1)).isoformat()
    frame = pd.DataFrame(
        [
            _pick_row(
                race_id="R1",
                horse_name="TodayA",
                card_date=today,
                off_time="18:00",
                ew_combined_ev=0.2,
            ),
            _pick_row(
                race_id="R2",
                horse_name="TodayB",
                card_date=today,
                off_time="19:00",
                ew_combined_ev=0.18,
            ),
            _pick_row(
                race_id="R3",
                horse_name="TomorrowA",
                card_date=tomorrow,
                course="York",
                off_time="14:00",
                ew_combined_ev=0.25,
            ),
            _pick_row(
                race_id="R4",
                horse_name="TomorrowB",
                card_date=tomorrow,
                course="Ascot",
                off_time="15:00",
                ew_combined_ev=0.21,
            ),
            _pick_row(
                race_id="R5",
                horse_name="TomorrowC",
                card_date=tomorrow,
                course="Newmarket",
                off_time="16:00",
                ew_combined_ev=0.17,
            ),
        ]
    )
    out = build_engine_combinations_by_day(frame, top_n=6)
    assert len(out["days"]) == 2
    today_day = next(d for d in out["days"] if d["card_date"] == today)
    tomorrow_day = next(d for d in out["days"] if d["card_date"] == tomorrow)
    assert today_day["day_label"] == "Today"
    assert tomorrow_day["day_label"] == "Tomorrow"
    assert [c["type"] for c in today_day["combinations"]] == ["double"]
    assert [c["type"] for c in tomorrow_day["combinations"]] == ["double", "trixie"]
    trixie_legs = tomorrow_day["combinations"][1]["legs"]
    assert all(leg["card_date"] == tomorrow for leg in trixie_legs)
    assert all("Tomorrow" in leg["event"] for leg in trixie_legs)
    assert "York" in trixie_legs[0]["event"]


def test_combinations_api_engine_fallback(tmp_path, monkeypatch):
    from hibs_racing.features.store import init_db
    from hibs_racing.tips.combinations_api import combinations_for_date
    from hibs_racing.tips import suggested_combinations as sc

    db = tmp_path / "racing.sqlite"
    init_db(db)
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))

    def _fake_engine(**_kwargs):
        return {
            "days": [
                {
                    "card_date": "2026-07-20",
                    "day_label": "Today",
                    "combinations": [
                        {
                            "type": "double",
                            "label": "Value lane double",
                            "bet_count": 1,
                            "pick_source": "value_lane",
                            "card_date": "2026-07-20",
                            "day_label": "Today",
                            "legs": [
                                {
                                    "selection": "Horse A",
                                    "event": "Today · York 14:00",
                                    "market": "each_way",
                                    "card_date": "2026-07-20",
                                    "day_label": "Today",
                                    "ew_combined_ev": 0.15,
                                },
                                {
                                    "selection": "Horse B",
                                    "event": "Today · Ascot 15:00",
                                    "market": "each_way",
                                    "card_date": "2026-07-20",
                                    "day_label": "Today",
                                    "ew_combined_ev": 0.12,
                                },
                            ],
                        }
                    ],
                    "singles": [],
                    "pick_count": 2,
                }
            ],
            "combinations": [
                {
                    "type": "double",
                    "label": "Value lane double",
                    "bet_count": 1,
                    "pick_source": "value_lane",
                    "legs": [
                        {"selection": "Horse A", "event": "Today · York 14:00", "market": "each_way", "ew_combined_ev": 0.15},
                        {"selection": "Horse B", "event": "Today · Ascot 15:00", "market": "each_way", "ew_combined_ev": 0.12},
                    ],
                }
            ],
            "singles": [],
            "pick_count": 2,
            "pick_source": "value_lane",
            "card_date": "2026-07-20",
            "day_label": "Today",
        }

    monkeypatch.setattr(sc, "build_engine_combinations_by_day", _fake_engine)
    payload = combinations_for_date(db, card_date="2026-07-20")
    assert payload["source"] == "engine"
    assert payload["pick_source"] == "value_lane"
    assert len(payload["combinations"]) == 1
    assert payload["combinations"][0]["type"] == "double"
    assert len(payload["days"]) == 1
    assert payload["days"][0]["day_label"] == "Today"
