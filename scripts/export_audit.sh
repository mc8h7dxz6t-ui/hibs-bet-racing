#!/usr/bin/env bash
# Inst++ audit room export — chain verify + gate report ZIP.
set -euo pipefail

DB_PATH="${1:-./data/inst_ledger.sqlite}"
OUT_DIR="${2:-./audit_bundle}"
PYTHON="${PYTHON:-python3}"

mkdir -p "$OUT_DIR"

"$PYTHON" - <<'PY' "$DB_PATH" "$OUT_DIR"
import json
import sys
from pathlib import Path

from inst_spine.check import run_institutional_check
from inst_spine.ledger import AppendOnlyLedger

db = Path(sys.argv[1])
out = Path(sys.argv[2])
ledger = AppendOnlyLedger(db)
entries = ledger.list_entries()
verify = ledger.verify()
report = run_institutional_check(ledger=ledger)

(out / "ledger_entries.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
(out / "verify.json").write_text(json.dumps(verify, indent=2), encoding="utf-8")
(out / "institutional_check.json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
(out / "genesis_anchor.json").write_text(
    (db.parent / f"{db.stem}.genesis.json").read_text(encoding="utf-8")
    if (db.parent / f"{db.stem}.genesis.json").exists()
    else "{}",
    encoding="utf-8",
)
(out / "wal_tail.json").write_text(
    json.dumps(ledger.wal.read_all()[-5:], indent=2),
    encoding="utf-8",
)
(out / "README.txt").write_text(
    "Inst++ audit bundle\n"
    f"entries: {len(entries)}\n"
    f"genesis_ok: {verify.get('genesis_ok')}\n"
    f"chain_ok: {verify.get('chain_ok')}\n"
    f"lamport_monotonic: {verify.get('lamport_monotonic')}\n"
    f"check_passed: {report.passed}\n",
    encoding="utf-8",
)
print(f"exported {len(entries)} entries to {out}")
PY

if command -v zip >/dev/null 2>&1; then
  (cd "$OUT_DIR" && zip -qr "../audit_bundle.zip" .)
  echo "wrote ${OUT_DIR%/}.zip"
fi
