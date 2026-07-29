"""Racing API guard — do not trip on parse/RP errors mislabeled as 403."""

from __future__ import annotations

from hibs_racing.racing_api_guard import clear_guard_state, should_record_api_forbidden


def test_should_not_record_nan_parse_error():
    exc = ValueError("cannot convert float NaN to integer")
    assert should_record_api_forbidden(exc) is False


def test_should_not_record_rp_cache_miss():
    exc = RuntimeError(
        "No cached RP racecards and live fetch disabled. "
        "Add EMAIL + ACCESS_TOKEN to .env, warm cards first, or set HIBS_RACING_RP_LIVE_FETCH=1."
    )
    assert should_record_api_forbidden(exc) is False


def test_should_record_real_403():
    exc = RuntimeError("Racing API 403 — plan 'pro' may not include endpoint")
    assert should_record_api_forbidden(exc) is True


def test_clear_guard_state_removes_file(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    guard_file = cache / "racing_api_guard_v1.json"
    guard_file.write_text('{"forbidden": {"at": "2026-07-29T00:00:00+00:00"}}', encoding="utf-8")
    monkeypatch.setenv("HIBS_RACING_CACHE_DIR", str(cache))
    clear_guard_state()
    assert not guard_file.is_file()
