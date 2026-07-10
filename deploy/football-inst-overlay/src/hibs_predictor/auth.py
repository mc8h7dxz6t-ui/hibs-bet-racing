"""Shared-password Flask auth for hibs-bet dashboard."""

from __future__ import annotations

import os
from functools import wraps
from typing import Callable, Optional
from urllib.parse import urlparse

from flask import Flask, abort, redirect, request, session, url_for
from werkzeug.security import check_password_hash


def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def auth_enabled() -> bool:
    return _env_truthy("HIBS_AUTH_ENABLED")


def public_health_enabled() -> bool:
    return _env_truthy("HIBS_AUTH_PUBLIC_HEALTH")


def public_tracker_enabled() -> bool:
    return _env_truthy("HIBS_AUTH_PUBLIC_TRACKER", "1")


def _secret_key() -> str:
    return (os.getenv("HIBS_SECRET_KEY") or os.getenv("FLASK_SECRET_KEY") or "").strip()


def _password_plain() -> str:
    return (os.getenv("HIBS_AUTH_PASSWORD") or os.getenv("HIBS_HIBS_PASSWORD") or "").strip()


def init_app(app: Flask) -> None:
    """Configure session auth; raises when auth enabled without secret key."""
    if auth_enabled() and not _secret_key():
        raise RuntimeError("HIBS_AUTH_ENABLED=1 requires HIBS_SECRET_KEY")
    if auth_enabled():
        app.secret_key = _secret_key() or "hibs-dev-insecure-change-me"
    else:
        app.secret_key = _secret_key() or "hibs-dev-no-auth"


def is_logged_in() -> bool:
    if not auth_enabled():
        return True
    return bool(session.get("hibs_authenticated"))


def login_user() -> None:
    session["hibs_authenticated"] = True
    session.permanent = True


def logout_user() -> None:
    session.pop("hibs_authenticated", None)


def check_password(password: str) -> bool:
    if not auth_enabled():
        return True
    supplied = (password or "").strip()
    expected = _password_plain()
    if not expected:
        return False
    if expected.startswith(("pbkdf2:", "scrypt:")):
        return check_password_hash(expected, supplied)
    return supplied == expected


def safe_next_url(raw: Optional[str]) -> str:
    if not raw:
        return url_for("index")
    parsed = urlparse(raw)
    if parsed.scheme or parsed.netloc:
        return url_for("index")
    if not raw.startswith("/"):
        return url_for("index")
    return raw


def _is_health_probe() -> bool:
    path = (request.path or "").rstrip("/")
    if path in ("/api/health", "/api/ping", "/api/status"):
        return True
    if path.startswith("/api/inst-pp/"):
        return True
    return False


def login_required(
    fn: Callable | None = None,
    *,
    allow_public_health: bool = False,
    allow_public_tracker: bool = False,
):
    def decorator(view: Callable):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not auth_enabled():
                return view(*args, **kwargs)
            if is_logged_in():
                return view(*args, **kwargs)
            if allow_public_health and public_health_enabled() and _is_health_probe():
                return view(*args, **kwargs)
            if allow_public_tracker and public_tracker_enabled():
                path = (request.path or "").rstrip("/")
                if path in ("/tracker", "/api/public-tracker", "/api/public-tracker.csv"):
                    return view(*args, **kwargs)
            if request.path.startswith("/api/"):
                abort(401)
            return redirect(url_for("login", next=request.full_path or request.path))

        return wrapped

    if fn is not None:
        return decorator(fn)
    return decorator
