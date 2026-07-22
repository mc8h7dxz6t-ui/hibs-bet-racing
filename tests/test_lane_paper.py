import pandas as pd

from hibs_racing.backtest.gate_impact import PARALLEL_FORWARD_LANES
from hibs_racing.cards.lane_paper import (
    attach_lane_flags,
    resolve_parallel_lane_specs,
    sync_parallel_lane_ledgers,
)
from hibs_racing.features.store import init_db
from hibs_racing.place.paper_ledger import record_paper_bet


def test_resolve_parallel_lane_specs_all_gates():
    cfg = {
        "paper_lanes": {
            "parallel_forward": {
                "enabled": True,
                "lanes": list(PARALLEL_FORWARD_LANES),
            }
        }
    }
    specs = resolve_parallel_lane_specs(cfg)
    assert len(specs) == len(PARALLEL_FORWARD_LANES)
    assert specs[0] == ("gate1", "flag_gate1")
    assert specs[-1] == ("gate11", "flag_gate11")


def test_attach_lane_flags_includes_gate1_and_gate11():
    frame = pd.DataFrame(
        {
            "race_id": ["r1"],
            "runner_id": ["x"],
            "card_date": ["2026-07-22"],
            "course": ["Ascot"],
            "off_time": ["14:30"],
            "horse_name": ["Test Horse"],
            "value_flag": [1],
            "flag_raw": [1],
            "model_score": [1.0],
            "model_win_prob": [0.5],
            "model_place_prob": [0.35],
            "combo_bayes_place": [0.30],
            "place_ev": [0.08],
            "ew_combined_ev": [0.10],
            "official_rating": [60],
            "trainer_rtf": [20],
            "data_quality_pct": [95],
            "field_size": [10],
            "win_decimal": [6.0],
            "place_fraction": [0.25],
            "places": [3],
            "race_name": ["Class 4 Handicap"],
        }
    )
    out = attach_lane_flags(frame)
    assert "flag_gate1" in out.columns
    assert "flag_gate7" in out.columns
    assert "flag_gate11" in out.columns


def test_sync_parallel_lane_ledgers_logs_per_lane(tmp_path):
    db = tmp_path / "lanes.db"
    init_db(db)
    scored = pd.DataFrame(
        [
            {
                "race_id": "r1",
                "runner_id": "runner-a",
                "card_date": "2026-07-22",
                "course": "Ascot",
                "off_time": "14:30",
                "horse_name": "Alpha",
                "flag_gate3": 1,
                "flag_gate7": 1,
                "flag_gate11": 0,
                "ew_combined_ev": 0.1,
                "win_decimal": 5.0,
                "place_fraction": 0.25,
                "places": 3,
            },
            {
                "race_id": "r2",
                "runner_id": "runner-b",
                "card_date": "2026-07-22",
                "course": "York",
                "off_time": "15:00",
                "horse_name": "Bravo",
                "flag_gate3": 0,
                "flag_gate7": 1,
                "flag_gate11": 0,
                "ew_combined_ev": 0.12,
                "win_decimal": 4.5,
                "place_fraction": 0.25,
                "places": 3,
            },
        ]
    )
    cfg = {
        "paper_lanes": {
            "parallel_forward": {
                "enabled": True,
                "lanes": ["gate3", "gate7"],
            }
        },
        "paper": {"default_stake": 1.0},
        "paths": {"db_path": str(db)},
    }
    from unittest.mock import patch

    with patch("hibs_racing.cards.lane_paper.load_config", return_value=cfg), patch(
        "hibs_racing.cards.lane_paper.db_path", return_value=db
    ), patch("hibs_racing.place.paper_ledger.load_config", return_value=cfg), patch(
        "hibs_racing.place.paper_ledger.db_path", return_value=db
    ):
        results = sync_parallel_lane_ledgers(scored, card_date="2026-07-22", database=db)
    assert len(results) == 2
    by_lane = {r["lane"]: r for r in results}
    assert by_lane["gate3"]["logged"] == 1
    assert by_lane["gate7"]["logged"] == 2

    from hibs_racing.features.store import connect

    with connect(db) as conn:
        rows = conn.execute(
            """
            SELECT paper_lane, horse_name, course, off_time, race_natural_key
            FROM paper_bets WHERE backtest = 0
            """
        ).fetchall()
    lanes = {r[0] for r in rows}
    assert lanes == {"gate3", "gate7"}
    assert all(r[1] and r[2] and r[3] and r[4] for r in rows)


def test_record_paper_bet_persists_context(tmp_path):
    db = tmp_path / "ctx.db"
    init_db(db)
    cfg = {"paths": {"db_path": str(db)}, "paper": {}}
    from unittest.mock import patch

    with patch("hibs_racing.place.paper_ledger.load_config", return_value=cfg), patch(
        "hibs_racing.place.paper_ledger.db_path", return_value=db
    ):
        record_paper_bet(
            "race-x",
            "runner-x",
            "each_way",
            1.0,
            is_value_pick=True,
            paper_lane="production",
            card_date="2026-07-22",
            course="Ascot",
            off_time="14:30",
            horse_name="Context Horse",
            race_natural_key="2026-07-22|ascot|14:30",
        )
    from hibs_racing.features.store import connect

    with connect(db) as conn:
        row = conn.execute(
            "SELECT card_date, course, off_time, horse_name, race_natural_key FROM paper_bets"
        ).fetchone()
    assert tuple(row) == ("2026-07-22", "Ascot", "14:30", "Context Horse", "2026-07-22|ascot|14:30")
