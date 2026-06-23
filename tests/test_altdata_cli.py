"""CLI integration tests — altdata poll, check, export."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "altdata.cli", *args],
        capture_output=True,
        text=True,
    )


def test_altdata_poll_check_export_verify(tmp_path: Path):
    db = tmp_path / "alt.sqlite"
    tar = tmp_path / "bundle.tar"
    ctx = '{"demo_price":99.0,"demo_seats":12,"demo_route":"LHR-JFK"}'
    poll = _run("poll", "--feed", "cli_feed", "--ctx", ctx, "--database", str(db))
    assert poll.returncode == 0, poll.stderr
    body = json.loads(poll.stdout)
    assert body["ok"] is True
    assert body["coverage_pct"] >= 85.0

    check = _run("check", "--database", str(db))
    assert check.returncode == 0, check.stderr
    assert json.loads(check.stdout)["passed"] is True

    export = _run("export", "--database", str(db), "--tarball", str(tar))
    assert export.returncode == 0, export.stderr
    assert json.loads(export.stdout)["ok"] is True

    verify = _run("verify-bundle", "--tarball", str(tar))
    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout)["ok"] is True


def test_altdata_coverage_error_exit(tmp_path: Path):
    db = tmp_path / "low.sqlite"
    ctx = '{"demo_price":1.0}'
    poll = _run(
        "poll",
        "--feed",
        "sparse",
        "--ctx",
        ctx,
        "--database",
        str(db),
        "--min-coverage",
        "99",
    )
    assert poll.returncode == 1
    err = json.loads(poll.stderr)
    assert err["ok"] is False
    assert err["error"]["code"] == "COVERAGE_FAIL"
