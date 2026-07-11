"""Ingress hardening — body limits, SSRF allowlists, fail-closed auth profiles."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Callable
from typing import Final
from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

DEFAULT_MAX_BODY_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MiB


def max_body_bytes() -> int:
    raw = os.getenv("INST_MAX_BODY_BYTES", "").strip()
    if not raw:
        return DEFAULT_MAX_BODY_BYTES
    try:
        return max(1024, int(raw))
    except ValueError:
        return DEFAULT_MAX_BODY_BYTES


def install_body_size_limit_middleware(
    app: ASGIApp,
    *,
    max_bytes: int | None = None,
    skip_paths: frozenset[str] | None = None,
) -> None:
    """Reject oversize Content-Length before body read — fail-closed DoS guard."""
    limit = max_bytes if max_bytes is not None else max_body_bytes()
    skips = skip_paths or frozenset({"/health", "/ready", "/"})

    @app.middleware("http")  # type: ignore[attr-defined]
    async def body_limit_guard(request: Request, call_next: Callable):
        if request.url.path in skips:
            return await call_next(request)
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > limit:
                    return JSONResponse(
                        {"error": "payload_too_large", "max_bytes": limit},
                        status_code=413,
                    )
            except ValueError:
                return JSONResponse({"error": "invalid_content_length"}, status_code=400)
        return await call_next(request)


def _is_blocked_host(hostname: str) -> bool:
    host = (hostname or "").strip().lower()
    if not host or host in ("localhost", "127.0.0.1", "::1"):
        return True
    if host.endswith(".local") or host.endswith(".internal"):
        return True
    try:
        addr = ipaddress.ip_address(host)
        return bool(
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
        )
    except ValueError:
        pass
    return False


def validate_forward_url(url: str, *, client_id: str = "") -> tuple[bool, str]:
    """
    SSRF guard for webhook forward targets.
    Requires https (or http only when INST_ALLOW_HTTP_FORWARD=1).
    Blocks private/link-local/metadata hosts.
    """
    raw = (url or "").strip()
    if not raw:
        return False, "empty_forward_url"
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    allow_http = os.getenv("INST_ALLOW_HTTP_FORWARD", "").strip().lower() in ("1", "true", "yes")
    if scheme not in ("https", "http"):
        return False, f"unsupported_scheme:{scheme}"
    if scheme == "http" and not allow_http:
        return False, "http_forward_disabled"
    if not parsed.hostname:
        return False, "missing_hostname"
    if _is_blocked_host(parsed.hostname):
        return False, f"blocked_host:{parsed.hostname}"
    allowlist = os.getenv("WEBHOOK_FORWARD_ALLOWLIST", "").strip()
    if allowlist:
        allowed = {h.strip().lower() for h in allowlist.split(",") if h.strip()}
        if parsed.hostname.lower() not in allowed:
            return False, f"host_not_allowlisted:{parsed.hostname}"
    return True, "ok"


def require_production_auth() -> bool:
    return os.getenv("INST_REQUIRE_API_KEYS", "").strip().lower() in ("1", "true", "yes")


def require_device_auth() -> bool:
    return os.getenv("INST_REQUIRE_DEVICE_AUTH", "").strip().lower() in ("1", "true", "yes")
