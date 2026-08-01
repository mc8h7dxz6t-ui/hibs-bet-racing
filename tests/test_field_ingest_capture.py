"""Layer 3 racing field capture into ingest spine."""

from __future__ import annotations

import sys
import types


def _runner_row(**overrides):
    base = {
        "runner_id": "r-9001",
        "race_natural_key": "2026-08-15|Ascot|14:30",
        "horse_name": "Layer Three",
        "source": "racing_api",
        "win_decimal": 4.5,
        "model_score": 0.66,
        "model_win_prob": 0.2,
        "model_place_prob": 0.4,
        "combo_bayes_place": 0.33,
        "jockey": "J Rider",
        "trainer": "T Handler",
        "official_rating": 88,
        "form_string": "2143",
        "card_comment": "Strong finish last time",
        "scoring_method": "lgbm_ranker",
        "enrich_source": "racing_post_scrape",
    }
    base.update(overrides)
    return base


def test_capture_racing_field_snapshots(tmp_path, monkeypatch):
    db = tmp_path / "ingest_spine.sqlite"
    monkeypatch.setenv("HIBS_INGEST_SPINE_DB", str(db))
    calls: list[dict] = []

    def _fake_upsert(**kwargs):
        calls.append(kwargs)
        return True

    fake_spine = types.SimpleNamespace(upsert_field_snapshot=_fake_upsert)
    fake_ingest = types.SimpleNamespace(spine_store=fake_spine)
    fake_predictor = types.SimpleNamespace(ingest=fake_ingest)
    monkeypatch.setitem(sys.modules, "hibs_predictor", fake_predictor)
    monkeypatch.setitem(sys.modules, "hibs_predictor.ingest", fake_ingest)
    monkeypatch.setitem(sys.modules, "hibs_predictor.ingest.spine_store", fake_spine)

    from hibs_racing.ingest.field_capture import capture_racing_field_snapshots

    out = capture_racing_field_snapshots([_runner_row()])
    assert out["runner_count"] == 1
    assert out["written"] == len(calls)
    assert calls[0]["sport"] == "racing"
    assert calls[0]["natural_key"] == "r-9001"
    assert {c["field_name"] for c in calls} >= {"win_odds", "model_score"}
