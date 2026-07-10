"""Shared HTTP hardening — API key and mTLS-forwarded identity hooks."""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Callable

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

# Paths that stay open when API key is configured (health probes, static UI).
DEFAULT_SKIP_PATHS = frozenset({"/health", "/ready", "/"})


def _expected_api_key(env_var: str) -> str:
    return os.getenv(env_var, "").strip()


def _extract_bearer_token(request: Request) -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("X-API-Key") or "").strip()


def verify_mtls_forwarded(request: Request) -> tuple[bool, str]:
    """
    When INST_MTLS_REQUIRED=1, require X-Client-Cert-CN from ingress (nginx/envoy).
    """
    if os.getenv("INST_MTLS_REQUIRED", "").strip().lower() not in ("1", "true", "yes"):
        return True, "mtls_not_required"
    cn = (request.headers.get("X-Client-Cert-CN") or "").strip()
    allowed = (os.getenv("INST_MTLS_ALLOWED_CN") or "").strip()
    if not allowed:
        return False, "mtls_required_but_INST_MTLS_ALLOWED_CN_unset"
    if cn != allowed:
        return False, f"mtls_cn_mismatch:{cn!r}"
    return True, "mtls_ok"


def device_token_hmac(device_id: str, *, secret: str) -> str:
    """Deterministic device token from shared secret + device_id."""
    return hmac.new(
        secret.encode("utf-8"),
        device_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]


def verify_device_token(device_id: str, token: str, *, secret_env: str = "HEALTH_DEVICE_AUTH_SECRET") -> bool:
    secret = os.getenv(secret_env, "").strip()
    if not secret:
        return True
    if not device_id or not token:
        return False
    expected = device_token_hmac(device_id, secret=secret)
    return hmac.compare_digest(expected, token.strip())


def verify_proxy_client_auth(request: Request, *, client_id: str) -> tuple[bool, str]:
    """
    When PROXY_CLIENT_AUTH_SECRET is set, require HMAC over client_id for ingress.
    Header: X-Proxy-Client-Signature = HMAC-SHA256(secret, client_id).
    """
    secret = os.getenv("PROXY_CLIENT_AUTH_SECRET", "").strip()
    if not secret:
        return True, "proxy_client_auth_not_required"
    sig = (request.headers.get("X-Proxy-Client-Signature") or "").strip()
    if not sig:
        return False, "missing_proxy_client_signature"
    expected = hmac.new(
        secret.encode("utf-8"),
        client_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False, "proxy_client_signature_mismatch"
    return True, "proxy_client_auth_ok"


def install_proxy_client_auth_middleware(app: ASGIApp) -> None:
    """Validate PROXY_CLIENT_AUTH on /v1/proxy/* and /v1/guard/* routes."""

    @app.middleware("http")  # type: ignore[attr-defined]
    async def proxy_client_guard(request: Request, call_next: Callable):
        path = request.url.path
        client_id = ""
        if path.startswith("/v1/proxy/"):
            client_id = path.split("/v1/proxy/", 1)[1].split("/", 1)[0]
        elif path.startswith("/v1/guard/"):
            client_id = path.split("/v1/guard/", 1)[1].split("/", 1)[0]
        elif path == "/v1/evaluate":
            secret = os.getenv("PROXY_CLIENT_AUTH_SECRET", "").strip()
            if secret:
                client_id = (request.headers.get("X-Inst-Client-Id") or "").strip()
                if not client_id:
                    return JSONResponse(
                        {"error": "unauthorized", "reason": "missing_x_inst_client_id"},
                        status_code=401,
                    )
        if client_id:
            ok, reason = verify_proxy_client_auth(request, client_id=client_id)
            if not ok:
                return JSONResponse({"error": "unauthorized", "reason": reason}, status_code=401)
        return await call_next(request)


def install_api_key_middleware(
    app: ASGIApp,
    *,
    env_var: str,
    skip_paths: frozenset[str] | None = None,
    skip_prefixes: tuple[str, ...] = ("/static",),
    require_mtls: bool = False,
) -> None:
    """
    Register HTTP middleware on a FastAPI/Starlette app.

    When *env_var* is unset, middleware is a no-op (local dev).
    When set, requests must send ``Authorization: Bearer <key>`` or ``X-API-Key``.
    """
    skips = skip_paths or DEFAULT_SKIP_PATHS

    @app.middleware("http")  # type: ignore[attr-defined]
    async def inst_api_key_guard(request: Request, call_next: Callable):
        path = request.url.path
        if path in skips or any(path.startswith(p) for p in skip_prefixes):
            return await call_next(request)

        if require_mtls or os.getenv("INST_MTLS_REQUIRED", "").strip().lower() in ("1", "true", "yes"):
            ok, reason = verify_mtls_forwarded(request)
            if not ok:
                return JSONResponse({"error": "unauthorized", "reason": reason}, status_code=401)

        expected = _expected_api_key(env_var)
        if not expected:
            return await call_next(request)

        token = _extract_bearer_token(request)
        if not token or not hmac.compare_digest(token, expected):
            return JSONResponse(
                {"error": "unauthorized", "message": f"valid API key required ({env_var})"},
                status_code=401,
            )
        return await call_next(request)
