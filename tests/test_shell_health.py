"""Shell health for HTML pages — fast path."""

from __future__ import annotations


def test_shell_health_status_fast(monkeypatch, tmp_path):
    from hibs_racing.web_service import shell_health_status

    db = tmp_path / "fs.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    monkeypatch.setenv("HIBS_RACING_FORCE_DISK", "1")

    hs = shell_health_status()
    assert hs.runners_loaded >= 0
    assert isinstance(hs.matchbook, bool)
