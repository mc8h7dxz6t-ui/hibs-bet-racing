#!/bin/bash
# HIBS Racing desktop launcher — local dashboard on http://127.0.0.1:5003
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

PORT="${HIBS_RACING_PORT:-5003}"
HOST="${HIBS_RACING_HOST:-127.0.0.1}"
URL="http://${HOST}:${PORT}"

for arg in "$@"; do
  case "$arg" in
    --help|-h)
      echo "Usage: hibs-racing-desktop-launch.sh"
      echo "  Starts the hibs-racing web UI and opens ${URL} in your browser."
      exit 0
      ;;
  esac
done

if [[ ! -d .venv ]]; then
  echo "Creating venv..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -e ".[dev,web]" -q

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  (sleep 2 && open "${URL}") &
fi

echo "HIBS Racing → ${URL}"
exec hibs-racing web --host "${HOST}" --port "${PORT}"
