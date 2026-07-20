"""Tests for daily Smart Portfolio digest and webhook notify."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_filter_smart_picks_value_dq_gate():
    from hibs_racing.daily.smart_picks import filter_smart_picks

    candidates = [
        {"value_flag": True, "data_quality_pct": 96, "steam_gate": "proceed", "place_score": 0.9, "horse_name": "A", "flag_gate3": 1},
        {"value_flag": False, "data_quality_pct": 96, "steam_gate": "proceed", "place_score": 0.95, "flag_gate3": 1},
        {"value_flag": True, "data_quality_pct": 70, "steam_gate": "proceed", "place_score": 0.99, "flag_gate3": 1},
        {"value_flag": True, "data_quality_pct": 96, "steam_gate": "abort", "place_score": 0.88, "flag_gate3": 1},
        {"value_flag": True, "data_quality_pct": 96, "steam_gate": "scale_up", "place_score": 0.85, "horse_name": "B", "flag_gate3": 1},
    ]
    picks = filter_smart_picks(candidates, limit=3)
    assert len(picks) == 2
    assert picks[0]["horse_name"] == "A"
    assert picks[1]["horse_name"] == "B"


def test_format_digest_message_no_picks():
    from hibs_racing.daily.smart_picks import format_digest_message

    text = format_digest_message({"picks": [], "card_dates": ["2026-05-29"]})
    assert "Engine refresh pending" in text
    assert "2026-05-29" in text

    engine = [
        {
            "display_rank": 1,
            "horse_name": "Alpha",
            "course": "York",
            "off_time": "14:00",
            "display_tier_label": "Engine lead",
            "pick_summary": "Top place blend.",
            "pick_reasons": ["Top place blend."],
            "pick_accuracy": {"accuracy_summary": "Blended place score 48%."},
        }
    ]
    text2 = format_digest_message({"picks": [], "engine_top_picks": engine, "card_dates": ["2026-05-29"]})
    assert "Alpha" in text2
    assert "Engine lead" in text2


def test_format_pick_line_includes_partner_link():
    from hibs_racing.daily.smart_picks import format_pick_line

    text = format_pick_line(
        {
            "horse_name": "Golden Fleece",
            "course": "Epsom",
            "off_time": "14:30",
            "data_quality_pct": 80,
            "steam_gate": "proceed",
            "model_place_prob": 0.55,
            "monetized_link": "https://www.matchbook.com?utm_source=hibs_racing_app",
        },
        1,
    )
    assert "Partner:" in text
    assert "utm_source=hibs_racing_app" in text


def test_webhook_skipped_when_unconfigured(monkeypatch):
    from hibs_racing.daily import webhook_notify

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    report = webhook_notify.notify_daily_digest()
    assert report["skipped"] is True


def test_notify_daily_digest_sends_telegram(monkeypatch):
    from hibs_racing.daily import webhook_notify

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    fake_payload = {
        "ok": True,
        "pick_count": 1,
        "picks": [
            {
                "horse_name": "Test Horse",
                "course": "Ascot",
                "off_time": "14:30",
                "data_quality_pct": 80,
                "steam_gate": "proceed",
                "model_place_prob": 0.55,
                "ew_combined_ev": 1.12,
                "win_decimal": 5.0,
            }
        ],
        "card_dates": ["2026-05-29"],
    }
    with patch.object(webhook_notify, "build_morning_smart_picks", return_value=fake_payload):
        with patch.object(webhook_notify, "send_telegram", return_value={"ok": True, "channel": "telegram"}):
            report = webhook_notify.notify_daily_digest(limit=3)
    assert report["ok"] is True
    assert report["pick_count"] == 1


def test_cli_notify_daily_skipped(capsys):
    from unittest.mock import patch

    from hibs_racing.cli import main

    with patch.dict("os.environ", {}, clear=True):
        rc = main(["notify-daily"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "skipped" in out.lower()
