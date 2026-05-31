from hibs_racing.portfolio.racing import _normalize_racing_row, build_racing_portfolio


def test_normalize_racing_row():
    row = {
        "bet_id": "b1",
        "horse_name": "Star",
        "course": "York",
        "card_date": "2026-06-15",
        "off_time": "15:30",
        "bet_type": "each_way",
        "stake_units": 1.0,
        "offered_win": 5.0,
        "model_ev": 0.08,
        "status": "placed",
        "result_pnl": 0.5,
        "race_id": "R1",
        "runner_id": "R1:h1",
        "is_value_pick": 1,
    }
    out = _normalize_racing_row(row)
    assert out["source"] == "hibs-racing"
    assert out["pnl"] == 0.5
    assert out["result"] == "W"


def test_build_racing_portfolio():
    payload = build_racing_portfolio()
    assert payload["ok"] is True
    assert payload["mode"] == "analytics"
    assert "summary" in payload
    assert "racing_pnl_units" in payload["summary"]
