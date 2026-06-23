#!/usr/bin/env bash
# Webhook Mesh WAL audit bundle — deterministic tar + SHA256 sidecar.
set -euo pipefail

WAL_PATH="${1:-./data/webhook_mesh.wal}"
OUT_TAR="${2:-./webhook_audit_bundle.tar}"
DLQ_DIR="${3:-./data/dead_letter}"
PYTHON="${PYTHON:-python3}"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

MANIFEST="$TMP_DIR/manifest.json"
SHA_FILE="${OUT_TAR}.sha256"

python3 - "$WAL_PATH" "$DLQ_DIR" "$MANIFEST" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

wal = Path(sys.argv[1])
dlq = Path(sys.argv[2])
out = Path(sys.argv[3])

payload = {
    "product": "webhook-mesh",
    "wal_path": str(wal),
    "wal_exists": wal.exists(),
    "wal_sha256": hashlib.sha256(wal.read_bytes()).hexdigest() if wal.exists() else None,
    "wal_line_count": sum(1 for line in wal.read_text(encoding="utf-8").splitlines() if line.strip()) if wal.exists() else 0,
    "dead_letter_entries": sorted(p.name for p in dlq.glob("*")) if dlq.exists() else [],
}
out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

if [[ -f "$WAL_PATH" ]]; then
  cp "$WAL_PATH" "$TMP_DIR/webhook_mesh.wal"
fi
if [[ -d "$DLQ_DIR" ]]; then
  mkdir -p "$TMP_DIR/dead_letter"
  cp -a "$DLQ_DIR/." "$TMP_DIR/dead_letter/" 2>/dev/null || true
fi

tar -cf "$OUT_TAR" -C "$TMP_DIR" .
sha256sum "$OUT_TAR" | awk '{print $1}' > "$SHA_FILE"
echo "webhook_audit_bundle=$OUT_TAR"
echo "sha256=$(cat "$SHA_FILE")"
