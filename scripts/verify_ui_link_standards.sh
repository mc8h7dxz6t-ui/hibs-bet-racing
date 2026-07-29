#!/usr/bin/env bash
# Racing UI link standards — product URLs + switcher template contract.
#
#   bash scripts/verify_ui_link_standards.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

PY=python3
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
fi

TPL="${ROOT}/templates/_product_switcher.html"
for marker in 'aria-selected=' 'data-product=' 'rel="noopener"' 'data-hibs-product-switch'; do
  if ! grep -qF "${marker}" "${TPL}"; then
    echo "FAIL: ${TPL} missing ${marker}" >&2
    exit 1
  fi
done
echo "product switcher template: ok"

JS="${ROOT}/static/hibs_product_switch.js"
if [[ ! -f "${JS}" ]]; then
  echo "FAIL: missing ${JS}" >&2
  exit 1
fi
echo "product switch JS present: ok"

echo "==> pytest product_links"
"${PY}" -m pip install -q -e ".[dev,web]" 2>/dev/null || "${PY}" -m pip install -q pytest 2>/dev/null || true
"${PY}" -m pytest tests/test_product_links.py tests/test_url_prefix.py -q --tb=short

echo "==> racing UI link standards: GREEN"
