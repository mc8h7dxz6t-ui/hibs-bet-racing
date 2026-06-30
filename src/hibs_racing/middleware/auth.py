"""API key auth for mutating hibs-racing routes."""

from __future__ import annotations

import os
import secrets
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from flask import jsonify, request

F = TypeVar("F", bound=Callable[..., Any])


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def configured_api_key() -> str:
    return (os.getenv("HIBS_RACING_API_KEY") or os.getenv("HIBS_RACING_MUTATE_API_KEY") or "").strip()


def auth_enabled() -> bool:
    """On when HIBS_RACING_API_AUTH=1 or production mode with a key configured."""
    raw = os.getenv("HIBS_RACING_API_AUTH")
    if raw is not None and str(raw).strip():
        return _env_truthy("HIBS_RACING_API_AUTH")
    from hibs_racing.models.ranker_preflight import is_production_mode

    if is_production_mode():
        return bool(configured_api_key())
    return False


def validate_auth_config() -> None:
    if auth_enabled() and not configured_api_key():
        raise RuntimeError(
            "HIBS_RACING_API_KEY is required when HIBS_RACING_API_AUTH=1 "
            "or HIBS_RACING_PRODUCTION is on"
        )


def _extract_api_key() -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header = (request.headers.get("X-Hibs-Api-Key") or "").strip()
    if header:
        return header
    return (request.args.get("api_key") or "").strip()


def _unauthorized():
    return jsonify({"ok": False, "error": "api_key_required"}), 401


def require_api_key(
    view: Optional[F] = None,
    *,
    methods: Optional[tuple[str, ...]] = None,
) -> Any:
    allowed = tuple(m.upper() for m in (methods or ("GET", "POST", "PUT", "PATCH", "DELETE")))

    def decorator(f: F) -> F:
        @wraps(f)
        def wrapped(*args: Any, **kwargs: Any):
            if not auth_enabled():
                return f(*args, **kwargs)
            if request.method.upper() not in allowed:
                return f(*args, **kwargs)
            expected = configured_api_key()
            provided = _extract_api_key()
            if not expected or not secrets.compare_digest(provided, expected):
                return _unauthorized()
            return f(*args, **kwargs)

        return wrapped  # type: ignore[return-value]

    if view is not None:
        return decorator(view)
    return decorator
