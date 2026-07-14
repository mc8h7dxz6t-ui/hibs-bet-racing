"""CLI integration tests — ad-guard evaluate, check, export."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ad_guard.cli", *args],
        capture_output=True,
        text=True,
    )


def _parse_json_objects(text: str) -> list[dict]:
    dec = json.JSONDecoder()
    idx = 0
    objs: list[dict] = []
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        obj, end = dec.raw_decode(text, idx)
        objs.append(obj)
        idx = end
    return objs


def test_ad_guard_evaluate_check_export_verify(tmp_path: Path):
    db = tmp_path / "ad.sqlite"
    tar = tmp_path / "bundle.tar"
    body = '{"campaignId":"cli-99","bidMicros":1000000,"costMicros":5000000}'

    ev = _run(
        "evaluate",
        "--provider",
        "google",
        "--body",
        body,
        "--database",
        str(db),
    )
    assert ev.returncode == 0, ev.stderr
    objs = _parse_json_objects(ev.stdout)
    assert objs[0]["decision"] == "approve"

    check = _run("check", "--database", str(db))
    assert check.returncode == 0, check.stderr
    assert json.loads(check.stdout)["passed"] is True

    export = _run("export", "--database", str(db), "--tarball", str(tar))
    assert export.returncode == 0, export.stderr
    assert json.loads(export.stdout)["ok"] is True

    verify = _run("verify-bundle", "--tarball", str(tar))
    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout)["ok"] is True
