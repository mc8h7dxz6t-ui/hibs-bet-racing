from hibs_racing.portfolio.unified import _football_pnl_units, _normalize_racing_row, build_unified_portfolio


def test_football_pnl_units_value_win():
    row = {"has_value": True, "value_result": "W", "value_odds": 3.5}
    assert _football_pnl_units(row) == 2.5


def test_football_pnl_units_value_loss():
    row = {"has_value": True, "value_result": "L", "value_odds": 3.5}
    assert _football_pnl_units(row) == -1.0


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


def test_build_unified_portfolio_racing_only(monkeypatch):
    monkeypatch.setenv("HIBS_BET_TRACKER_URL", "http://127.0.0.1:9/invalid")
    monkeypatch.delenv("HIBS_BET_DB_PATH", raising=False)
    payload = build_unified_portfolio()
    assert payload["ok"] is True
    assert "summary" in payload
    assert payload["football_source"] in ("none", "sqlite:") or payload["football_source"].startswith("sqlite:")
