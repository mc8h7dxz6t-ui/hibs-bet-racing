#!/bin/bash
# Mac-friendly launcher — use python3 (macOS has no `python` on PATH by default).
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d .venv ]]; then
  echo "Creating venv with python3..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [[ "${1:-}" == "web" || "${1:-}" == "ui" ]]; then
  shift || true
  pip install -e ".[dev,web]" -q
  exec hibs-racing web "$@"
fi

pip install -e ".[dev]" -q
exec hibs-racing "$@"
