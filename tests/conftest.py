"""Institutional test harness — resource limits and hygiene."""

from __future__ import annotations

import gc
import sys

import pytest


def pytest_sessionstart(session: pytest.Session) -> None:
    """Raise open-file limit on macOS before SQLite-heavy suite."""
    if sys.platform != "darwin":
        return
    try:
        import resource

        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = min(max(soft, 4096), hard)
        if target > soft:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    except (ImportError, OSError, ValueError):
        pass


def pytest_configure(config: pytest.Config) -> None:
    if sys.version_info >= (3, 14):
        config.issue_config_time_warning(
            pytest.PytestConfigWarning(
                "Python 3.14+ is experimental for institutional tests; "
                "use Python 3.10–3.13 for gold-standard CI parity."
            ),
            stacklevel=2,
        )


@pytest.fixture(autouse=True)
def _institutional_test_hygiene():
    yield
    try:
        from inst_spine.ledger_registry import clear_ledger_registry

        clear_ledger_registry()
    except Exception:
        pass
    gc.collect()
