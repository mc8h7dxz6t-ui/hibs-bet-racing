#!/usr/bin/env bash
# Remove corrupted pip leftovers (~package dirs) and reinstall hibs-racing editable.
#
#   sudo bash /opt/hibs-bet/scripts/repair_racing_venv_pip.sh
set -euo pipefail

RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
VENV="${RACING}/.venv"

[[ -d "${RACING}" ]] || { echo "missing ${RACING}" >&2; exit 1; }
[[ -x "${VENV}/bin/pip" ]] || { echo "missing ${VENV}/bin/pip" >&2; exit 1; }

echo "==> remove corrupted pip metadata (~ibs-racing etc.)"
find "${VENV}/lib" \( -type d -o -type f \) -name '~*' -print -exec rm -rf {} + 2>/dev/null || true
# Some pip versions leave a literal ~ibs-racing folder without glob match edge cases
rm -rf "${VENV}/lib"/python*/site-packages/~ibs-racing* 2>/dev/null || true

echo "==> reinstall hibs-racing"
cd "${RACING}"
export HOME="${RACING}"
sudo -u www-data env HOME="${RACING}" PIP_CACHE_DIR="${RACING}/.cache/pip" \
  "${VENV}/bin/pip" install -q -r requirements.txt
[[ -f pyproject.toml || -f setup.py ]] && \
  sudo -u www-data env HOME="${RACING}" PIP_CACHE_DIR="${RACING}/.cache/pip" \
    "${VENV}/bin/pip" install -q -e .

mkdir -p "${RACING}/.cache/pip"
chown -R www-data:www-data "${RACING}/.cache" 2>/dev/null || true

echo "==> verify (should be silent — no ~ibs-racing warnings)"
sudo -u www-data env HOME="${RACING}" "${VENV}/bin/pip" check 2>&1 | head -5 || true
sudo -u www-data env HOME="${RACING}" PYTHONPATH="${RACING}/src" \
  "${VENV}/bin/python3" -c "import hibs_racing; print('hibs_racing import OK')"
