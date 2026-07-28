"""RP racecard cache-first behaviour without live credentials."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest


def test_fetch_racecards_uses_cache_without_live(monkeypatch, tmp_path: Path) -> None:
    from hibs_racing.ingest import racecards as rc

    today = date.today().isoformat()
    cards_dir = tmp_path / "racecards"
    cards_dir.mkdir()
    cached = cards_dir / f"{today}.json"
    cached.write_text('{"gb": {"Ascot": {"14:30": {"runners": [{"name": "A"}]}}}}' * 3, encoding="utf-8")
    monkeypatch.setattr(rc, "RPSCRAPE_RACECARDS", cards_dir)

    def _boom(*_a, **_k):
        raise AssertionError("subprocess should not run when cache hit")

    monkeypatch.setattr(rc.subprocess, "run", _boom)
    paths = rc.fetch_racecards(day=1, region="gb", allow_live=False)
    assert paths == [cached]


def test_fetch_racecards_skips_live_without_creds(monkeypatch, tmp_path: Path) -> None:
    from hibs_racing.ingest import racecards as rc

    cards_dir = tmp_path / "racecards"
    cards_dir.mkdir()
    monkeypatch.setattr(rc, "RPSCRAPE_RACECARDS", cards_dir)
    monkeypatch.setattr(rc, "_load_env", lambda: {})
    monkeypatch.setattr(rc, "_sync_rpscrape_dotenv", lambda: {})

    with pytest.raises(RuntimeError, match="live fetch disabled"):
        rc.fetch_racecards(day=1, region="gb", allow_live=False)
