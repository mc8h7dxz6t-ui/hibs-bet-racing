"""Trading daemon runtime paths — disk fallback when /var/run/hibs blocked."""

from __future__ import annotations

import json

import pytest


def test_write_heartbeat_uses_runtime_dir(tmp_path, monkeypatch):
    from hibs_racing.trading import status_plane

    run_dir = tmp_path / "run"
    monkeypatch.setenv("HIBS_RACING_RUNTIME_DIR", str(run_dir))
    monkeypatch.delenv("HIBS_TRADING_STATUS_FILE", raising=False)
    status_plane.write_heartbeat(payload={"component": "test"})
    out = run_dir / "trading_daemon.json"
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["component"] == "test"


def test_write_heartbeat_falls_back_when_var_run_blocked(tmp_path, monkeypatch):
    from hibs_racing.trading import status_plane

    run_dir = tmp_path / "run"
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(0o500)
    monkeypatch.setenv("HIBS_TRADING_STATUS_FILE", str(blocked / "trading_daemon.json"))
    monkeypatch.setenv("HIBS_RACING_RUNTIME_DIR", str(run_dir))
    status_plane.write_heartbeat(payload={"fallback": True})
    assert (run_dir / "trading_daemon.json").is_file()
