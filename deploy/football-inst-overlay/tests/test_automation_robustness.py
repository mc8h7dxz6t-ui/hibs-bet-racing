"""Automation robustness tests — cron installers and alert scripts."""

from __future__ import annotations


def test_alert_f7_deferred_without_matchdays(monkeypatch):
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setenv("HIBS_CLV_LOG_ENABLED", "1")
    import runpy
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "alert_f7_capture_regression.py"
    try:
        runpy.run_path(str(path), run_name="__main__")
        rc = 0
    except SystemExit as exc:
        rc = int(exc.code) if exc.code is not None else 1
    assert rc == 0


def test_run_daily_audit_log_disabled(monkeypatch):
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "0")
    import runpy
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "run_daily_audit_log.py"
    try:
        runpy.run_path(str(path), run_name="__main__")
        rc = 0
    except SystemExit as exc:
        rc = int(exc.code) if exc.code is not None else 1
    assert rc == 1


def test_cron_markers_defined():
    from hibs_predictor.inst_pp_snapshot import _EXPECTED_CRON_MARKERS

    assert "hibs-bet: daily bundle" in _EXPECTED_CRON_MARKERS
    assert "hibs-bet: hands-off cycle" in _EXPECTED_CRON_MARKERS
