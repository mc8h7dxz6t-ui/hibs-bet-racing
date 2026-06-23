"""CLI integration tests — ai-kit run, check, export."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ai_kit.cli", *args],
        capture_output=True,
        text=True,
    )


def test_ai_kit_run_check_export_verify(tmp_path: Path):
    trace = tmp_path / "trace.sqlite"
    checkpoint = tmp_path / "checkpoint.sqlite"
    tar = tmp_path / "bundle.tar"

    run = _run("run", "--steps", "2", "--trace-db", str(trace), "--checkpoint-db", str(checkpoint))
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["product"] == "ai-kit"

    check = _run("check", "--database", str(trace))
    assert check.returncode == 0, check.stderr
    assert json.loads(check.stdout)["passed"] is True

    export = _run("export", "--database", str(trace), "--tarball", str(tar))
    assert export.returncode == 0, export.stderr
    assert json.loads(export.stdout)["ok"] is True

    verify = _run("verify-bundle", "--tarball", str(tar))
    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout)["ok"] is True


def test_ai_kit_validate_demo():
    ok = _run("validate-demo", "--raw", '{"ok":true}')
    assert ok.returncode == 0
    assert json.loads(ok.stdout)["ok"] is True

    bad = _run("validate-demo", "--raw", '{"missing":true}')
    assert bad.returncode == 1
