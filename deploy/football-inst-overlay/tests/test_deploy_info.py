"""Tests for deploy_info ping metadata."""

from __future__ import annotations

from pathlib import Path


def test_gather_deploy_info_reads_deploy_revision(tmp_path, monkeypatch):
    monkeypatch.setenv("DEPLOY_PATH", str(tmp_path))
    monkeypatch.setenv("HIBS_DOMAIN", "example.test")
    (tmp_path / ".deploy-revision").write_text(
        "revision=main@football-inst-overlay\n"
        "deployed_at=2026-07-10T19:00:00Z\n"
        "deploy_host=ubuntu\n"
        "service=hibs-bet\n",
        encoding="utf-8",
    )

    from hibs_predictor.deploy_info import gather_deploy_info

    info = gather_deploy_info()
    assert info["revision"] == "main@football-inst-overlay"
    assert info["deployed_at"] == "2026-07-10T19:00:00Z"
    assert info["deploy_host"] == "ubuntu"
    assert info["service"] == "hibs-bet"
    assert info["repo_root"] == str(tmp_path)
    assert info["production_url"] == "https://example.test"
