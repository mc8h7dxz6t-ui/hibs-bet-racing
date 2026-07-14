"""CLI integration tests — structured errors and exit codes."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "compliance_log.cli", *args],
        capture_output=True,
        text=True,
    )


def test_compliance_ingest_and_check(tmp_path: Path):
    db = tmp_path / "cli.sqlite"
    snap = tmp_path / "snap.json"
    snap.write_text('{"action":"approve","amount":100,"customer_id":"c1"}', encoding="utf-8")
    r = _run(
        "ingest",
        "--snapshot",
        str(snap),
        "--outcome",
        '{"status":"ok"}',
        "--database",
        str(db),
    )
    assert r.returncode == 0
    entry = json.loads(r.stdout)
    assert entry["event_type"] == "decision"

    check = _run("check", "--database", str(db))
    assert check.returncode == 0
    report = json.loads(check.stdout)
    assert report["passed"] is True


def test_compliance_invalid_manifest_errors(tmp_path: Path):
    db = tmp_path / "bad.sqlite"
    snap = tmp_path / "snap.json"
    man = tmp_path / "man.json"
    snap.write_text("{}", encoding="utf-8")
    man.write_text("{}", encoding="utf-8")
    r = _run(
        "ingest",
        "--snapshot",
        str(snap),
        "--manifest",
        str(man),
        "--database",
        str(db),
    )
    assert r.returncode == 1
    err = json.loads(r.stderr)
    assert err["ok"] is False
    assert err["error"]["code"] == "INGEST_VALIDATION"


def test_compliance_export_verify_bundle(tmp_path: Path):
    db = tmp_path / "exp.sqlite"
    snap = tmp_path / "snap.json"
    snap.write_text('{"action":"approve","amount":1,"customer_id":"x"}', encoding="utf-8")
    _run("ingest", "--snapshot", str(snap), "--database", str(db))
    tar = tmp_path / "bundle.tar"
    exp = _run("export", "--database", str(db), "--tarball", str(tar))
    assert exp.returncode == 0
    body = json.loads(exp.stdout)
    assert body["product"] == "compliance-logger"

    verify = _run("verify-bundle", "--tarball", str(tar))
    assert verify.returncode == 0
    assert json.loads(verify.stdout)["ok"] is True
