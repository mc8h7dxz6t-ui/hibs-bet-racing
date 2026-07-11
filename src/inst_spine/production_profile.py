"""Production profile gates — fail-closed /ready when HA dependencies missing."""

from __future__ import annotations

import os
from typing import Final

from inst_spine.health_probes import redis_ready_from_env
from inst_spine.ledger_factory import is_postgres_dsn

_TRUTHY: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})


def _flag(name: str, default: str = "") -> bool:
    return os.getenv(name, default).strip().lower() in _TRUTHY


def production_profile_enabled() -> bool:
    """INST_PRODUCTION_PROFILE=1 — enforce Redis/Postgres/durable dispatch on /ready."""
    return _flag("INST_PRODUCTION_PROFILE")


def memory_backends_allowed() -> bool:
    """INST_FORCE_MEMORY_BACKENDS=1 — dev/test escape hatch (never in prod profile)."""
    if production_profile_enabled():
        return False
    return _flag("INST_FORCE_MEMORY_BACKENDS")


def redis_required_for_production() -> bool:
    if memory_backends_allowed():
        return False
    if production_profile_enabled():
        return True
    return _flag("INST_REQUIRE_REDIS")


def redis_production_check(*, env_var: str = "INST_REDIS_URL") -> tuple[bool, str]:
    """Return (ok, detail) for multi-instance Redis profile."""
    if not redis_required_for_production():
        return True, "redis_not_required"
    url = os.getenv(env_var, "").strip()
    if not url:
        return False, f"{env_var}_required_for_production_profile"
    return redis_ready_from_env(env_var=env_var)


def postgres_ha_check(database: str | None = None) -> tuple[bool, str]:
    """When INST_REQUIRE_POSTGRES=1 or DB is already a Postgres DSN, verify connectivity."""
    dsn = (database or os.getenv("INST_POSTGRES_DSN", "")).strip()
    require = _flag("INST_REQUIRE_POSTGRES") or production_profile_enabled()
    if not require and not is_postgres_dsn(dsn):
        return True, "postgres_not_required"
    if not dsn:
        return False, "postgres_dsn_required_for_production_profile"
    if not is_postgres_dsn(dsn):
        return False, "postgres_dsn_invalid"
    try:
        from inst_spine.ledger_factory import open_ledger

        ledger = open_ledger(dsn)
        verify = ledger.verify()
        if not verify.get("chain_ok", True) and verify.get("entries", 0):
            return False, f"postgres_chain_broken:{verify}"
        return True, "postgres_ok"
    except Exception as exc:
        return False, f"postgres_error:{exc}"


def durable_webhook_dispatch_required() -> bool:
    if memory_backends_allowed():
        return False
    if production_profile_enabled():
        return True
    return _flag("WEBHOOK_REQUIRE_REDIS_DISPATCH")


def webhook_dispatch_check(dispatch_mode: str) -> tuple[bool, str]:
    if not durable_webhook_dispatch_required():
        return True, "durable_dispatch_not_required"
    if dispatch_mode == "redis":
        ok, detail = redis_production_check()
        return ok, f"redis_stream:{detail}"
    return False, "background_dispatch_not_allowed_in_production_profile"


def drift_redis_rolling_required() -> bool:
    if memory_backends_allowed():
        return False
    if production_profile_enabled():
        return True
    return _flag("DRIFT_GATE_REQUIRE_REDIS")


def drift_redis_check() -> tuple[bool, str]:
    if not drift_redis_rolling_required():
        return True, "drift_redis_not_required"
    return redis_production_check()
