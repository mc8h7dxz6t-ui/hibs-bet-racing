"""Tests for detailed daily email digest."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hibs_racing.daily.email_digest import (
    email_digest_configured,
    format_email_digest_text,
    send_daily_email_digest,
    smtp_use_ssl,
)
from hibs_racing.daily.smart_picks import build_morning_smart_picks_explained


def test_email_not_configured():
    assert email_digest_configured() is False
    report = send_daily_email_digest(limit=3)
    assert report.get("skipped") is True


def test_format_email_includes_reasons():
    payload = {
        "pick_count": 1,
        "candidate_count": 10,
        "card_dates": ["2026-05-29"],
        "generated_at": "2026-05-29T06:01:00+00:00",
        "picks": [
            {
                "horse_name": "Golden Fleece",
                "course": "Epsom",
                "off_time": "14:30",
                "card_date": "2026-05-29",
                "race_name": "Handicap",
                "value_flag": True,
                "data_quality_pct": 82,
                "steam_gate": "proceed",
                "model_place_prob": 0.52,
                "combo_bayes_place": 0.41,
                "ew_combined_ev": 0.15,
                "win_decimal": 5.0,
                "places": 3,
                "place_fraction": 0.25,
                "pick_reasons": ["Strong combo prior.", "Passes value gates."],
            }
        ],
    }
    text = format_email_digest_text(payload)
    assert "Golden Fleece" in text
    assert "14:30" in text
    assert "Strong combo prior" in text
    assert "Data quality: 82%" in text


def test_smtp_use_ssl_port_465(monkeypatch):
    monkeypatch.delenv("SMTP_USE_SSL", raising=False)
    monkeypatch.delenv("SMTP_SSL", raising=False)
    assert smtp_use_ssl(465) is True
    assert smtp_use_ssl(587) is False


def test_smtp_use_ssl_env_flag(monkeypatch):
    monkeypatch.setenv("SMTP_USE_SSL", "1")
    assert smtp_use_ssl(587) is True
    monkeypatch.setenv("SMTP_USE_SSL", "0")
    assert smtp_use_ssl(587) is False


def test_send_email_mock_smtp(monkeypatch):
    monkeypatch.setenv("HIBS_DAILY_EMAIL_TO", "trial@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    fake_payload = {
        "ok": True,
        "pick_count": 1,
        "picks": [{"horse_name": "A", "pick_reasons": ["x"], "value_flag": True, "data_quality_pct": 80}],
        "card_dates": ["2026-05-29"],
        "candidate_count": 5,
        "generated_at": "2026-05-29T06:00:00+00:00",
    }
    mock_smtp = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_smtp.return_value
    with patch(
        "hibs_racing.daily.email_digest.build_morning_smart_picks_explained",
        return_value=fake_payload,
    ):
        with patch("hibs_racing.daily.email_digest.smtplib.SMTP", mock_smtp):
            report = send_daily_email_digest(limit=3)
    assert report.get("ok") is True
    assert report.get("to") == ["trial@example.com"]


def test_send_email_mock_smtp_ssl(monkeypatch):
    monkeypatch.setenv("HIBS_DAILY_EMAIL_TO", "trial@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.tools.sky.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_FROM", "sender@sky.com")
    monkeypatch.setenv("SMTP_USER", "sender@sky.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    fake_payload = {
        "ok": True,
        "pick_count": 0,
        "picks": [],
        "card_dates": ["2026-05-29"],
        "candidate_count": 0,
        "generated_at": "2026-05-29T06:00:00+00:00",
    }
    mock_ssl = MagicMock()
    mock_ssl.return_value.__enter__.return_value = mock_ssl.return_value
    with patch(
        "hibs_racing.daily.email_digest.build_morning_smart_picks_explained",
        return_value=fake_payload,
    ):
        with patch("hibs_racing.daily.email_digest.smtplib.SMTP_SSL", mock_ssl):
            with patch("hibs_racing.daily.email_digest.smtplib.SMTP") as mock_plain:
                report = send_daily_email_digest(limit=3)
    assert report.get("ok") is True
    mock_ssl.assert_called_once()
    mock_plain.assert_not_called()
    mock_ssl.return_value.__enter__.return_value.login.assert_called_once()


def test_explained_build_adds_pick_reasons(monkeypatch):
    from hibs_racing.daily import smart_picks as sp

    monkeypatch.setattr(
        sp,
        "build_morning_smart_picks",
        lambda **kw: {
            "ok": True,
            "pick_count": 1,
            "picks": [{"runner_id": "r1", "horse_name": "Horse A", "value_flag": True}],
            "card_dates": ["2026-05-29"],
            "candidate_count": 1,
        },
    )
    import pandas as pd

    frame = pd.DataFrame(
        [
            {
                "runner_id": "r1",
                "race_id": "race1",
                "horse_name": "Horse A",
                "jockey": "J Bloggs",
                "trainer": "T Smith",
                "combo_bayes_place": 0.5,
                "model_place_prob": 0.48,
                "value_flag": 1,
            }
        ]
    )
    monkeypatch.setattr(sp, "load_scored_cards", lambda: frame)
    out = build_morning_smart_picks_explained(limit=1)
    assert out["picks"][0].get("pick_reasons")
