"""Institutional readiness checks."""

from __future__ import annotations

import pytest


def test_readiness_dict_shape(monkeypatch):
    monkeypatch.delenv("HIBS_PRODUCTION", raising=False)
    from hibs_predictor.institutional_readiness import readiness_dict

    rep = readiness_dict()
    assert "engineering_grade" in rep
    assert "evidence_grade" in rep
    assert "blocking_issues" in rep
    assert "warnings" in rep
    assert "nine_ten" in rep


def test_production_blocks_dev_full_dq(monkeypatch):
    monkeypatch.setenv("HIBS_PRODUCTION", "1")
    monkeypatch.setenv("HIBS_DEV_FULL_DQ", "1")
    from hibs_predictor.institutional_readiness import collect_config_issues

    issues, _warnings = collect_config_issues(production=True)
    assert any("HIBS_DEV_FULL_DQ" in i for i in issues)


def test_validate_production_raises_on_dev_dq(monkeypatch):
    monkeypatch.setenv("HIBS_PRODUCTION", "1")
    monkeypatch.setenv("HIBS_DEV_FULL_DQ", "1")
    from hibs_predictor.institutional_readiness import validate_production_config

    with pytest.raises(RuntimeError, match="HIBS_DEV_FULL_DQ"):
        validate_production_config(strict=True)


def test_engineering_grade_a_requires_no_warnings(monkeypatch):
    monkeypatch.setenv("HIBS_PRODUCTION", "1")
    monkeypatch.delenv("HIBS_DEV_FULL_DQ", raising=False)
    monkeypatch.delenv("HIBS_FETCH_ALL_DOMESTIC", raising=False)
    monkeypatch.setenv("HIBS_PREDICTION_LOG_ENABLED", "1")
    monkeypatch.setenv("HIBS_CLV_LOG_ENABLED", "1")
    monkeypatch.setenv("HIBS_SHARPEN_GATES", "1")
    monkeypatch.setenv(
        "HIBS_VALUE_LEAGUES",
        "EPL,SCOTLAND,UCL,EUROPA_LEAGUE,UECL,LA_LIGA,SERIE_A,BUNDESLIGA,LIGUE_1,EREDIVISIE,PRIMEIRA",
    )
    monkeypatch.setenv("HIBS_AUTH_ENABLED", "0")
    from hibs_predictor.institutional_readiness import readiness_dict

    rep = readiness_dict()
    assert rep["engineering_grade"] == "B+"
    assert rep["warnings"]


def test_auth_production_requires_secret(monkeypatch):
    monkeypatch.setenv("HIBS_PRODUCTION", "1")
    monkeypatch.setenv("HIBS_AUTH_ENABLED", "1")
    monkeypatch.delenv("HIBS_SECRET_KEY", raising=False)
    from flask import Flask
    from hibs_predictor.auth import init_app

    app = Flask(__name__)
    with pytest.raises(RuntimeError, match="HIBS_SECRET_KEY"):
        init_app(app)
