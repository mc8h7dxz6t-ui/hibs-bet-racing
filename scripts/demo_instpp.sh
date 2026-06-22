#!/usr/bin/env bash
# Inst++ buyer demo — Compliance Logger (#1) + Proxy-Risk Gateway (#2) in one command.
#
# Usage:
#   ./scripts/demo_instpp.sh              # full demo (includes live httpbin forward)
#   SKIP_LIVE=1 ./scripts/demo_instpp.sh  # offline-safe (no external HTTP)
#   ./scripts/demo_instpp.sh --clean      # wipe data/demo first
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"

banner() {
  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  printf "║  %-60s║\n" "$1"
  echo "╚══════════════════════════════════════════════════════════════╝"
  echo ""
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "Usage: ./scripts/demo_instpp.sh [--clean]"
  echo ""
  echo "  Runs both Inst++ gold-standard demos:"
  echo "    1. Compliance Logger  — ingest → F1–F9 → export → verify-bundle"
  echo "    2. Proxy-Risk       — shadow → live forward → export → verify-bundle"
  echo ""
  echo "  Environment:"
  echo "    SKIP_LIVE=1   Skip live httpbin forward (offline / air-gapped)"
  echo "    PYTHON=...    Python interpreter (default: python3)"
  echo ""
  echo "  Artifacts: data/demo/"
  exit 0
fi

if [[ "${1:-}" == "--clean" ]]; then
  echo "==> Cleaning data/demo/"
  rm -rf data/demo
fi

mkdir -p data/demo

banner "Inst++ DEMO — install dependencies"
pip install -e ".[dev,instpp]" -q

banner "1/2 — Compliance Logger"
./scripts/demo_compliance_logger.sh \
  data/demo/compliance.sqlite \
  data/demo/compliance_bundle \
  data/demo/compliance_bundle.tar

banner "2/2 — Proxy-Risk Gateway"
export SKIP_LIVE="${SKIP_LIVE:-0}"
./scripts/demo_proxy_risk.sh \
  data/demo/proxy.sqlite \
  data/demo/proxy_bundle \
  data/demo/proxy_bundle.tar

banner "DEMO COMPLETE"
"$PYTHON" - <<'PY'
import json
from pathlib import Path

demo = Path("data/demo")

def sidecar(path: Path) -> dict | None:
    p = path.with_suffix(path.suffix + ".sha256.json")
    if not p.exists():
        return None
    import json
    return json.loads(p.read_text(encoding="utf-8"))

artifacts = {
    "compliance": {
        "database": str(demo / "compliance.sqlite"),
        "tarball": str(demo / "compliance_bundle.tar"),
        "sidecar": sidecar(demo / "compliance_bundle.tar"),
    },
    "proxy_risk": {
        "database": str(demo / "proxy.sqlite"),
        "tarball": str(demo / "proxy_bundle.tar"),
        "sidecar": sidecar(demo / "proxy_bundle.tar"),
    },
}
print(json.dumps({"status": "PASSED", "artifacts": artifacts}, indent=2))
PY

echo ""
echo "Next steps:"
echo "  compliance-log verify-bundle --tarball data/demo/compliance_bundle.tar"
echo "  proxy-risk verify-bundle --tarball data/demo/proxy_bundle.tar"
echo "  inst-workflow serve --port 8790   # browser workflow UI → http://127.0.0.1:8790"
echo "  ./scripts/instpp_rigorous_test.sh   # full test + log"
echo ""
