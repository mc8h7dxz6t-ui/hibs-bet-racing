#!/usr/bin/env bash
# Shared bootstrap for institutional test scripts — macOS FD limits, Python check, pytest hygiene.
# Source from instpp_smoke_test.sh and instpp_rigorous_test.sh.

instpp_raise_ulimit() {
  if [ "$(uname -s)" = "Darwin" ]; then
    ulimit -n 10240 2>/dev/null || ulimit -n 4096 2>/dev/null || ulimit -n 2048 2>/dev/null || true
  fi
}

instpp_prune_pytest_tmp() {
  local base="${PYTEST_TMPDIR:-${TMPDIR:-/tmp}}"
  local user
  user="$(whoami 2>/dev/null || id -un 2>/dev/null || echo user)"
  local root="$base/pytest-of-$user"
  [ -d "$root" ] || return 0
  # Keep newest 3 session dirs; prune older (prevents Errno 24 on macOS).
  find "$root" -mindepth 1 -maxdepth 1 -type d 2>/dev/null \
    | sort -r \
    | tail -n +4 \
    | while IFS= read -r d; do
      rm -rf "$d" 2>/dev/null || true
    done
}

instpp_check_python() {
  local py="${PYTHON:-python3}"
  if ! "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "[FAIL] Python 3.10+ required (found $($py --version 2>&1))" >&2
    exit 1
  fi
  if "$py" -c 'import sys; sys.exit(0 if sys.version_info < (3, 14) else 1)'; then
    return 0
  fi
  echo "WARNING: Python 3.14+ is experimental — institutional CI uses 3.10–3.13." >&2
  echo "         Recommend: brew install python@3.12 && python3.12 -m venv .venv" >&2
}

instpp_bootstrap() {
  instpp_check_python
  instpp_raise_ulimit
  instpp_prune_pytest_tmp
}
