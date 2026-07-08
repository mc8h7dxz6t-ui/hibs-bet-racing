"""Backtest results summary for health/tracker."""

from hibs_racing.analytics.backtest_results import backtest_results_summary


def test_backtest_results_summary_empty_db(tmp_path, monkeypatch):
    db = tmp_path / "t.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    out = backtest_results_summary()
    assert "forward" in out
    assert "backtest" in out
    assert "roi_disclaimer" in out
