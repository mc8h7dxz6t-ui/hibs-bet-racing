"""FastAPI lifespan and JSON error envelope — production serve standard."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from starlette.responses import Response

StartupFn = Callable[[], None | Awaitable[None]]
ShutdownFn = Callable[[], None | Awaitable[None]]


def make_lifespan(on_startup: StartupFn, on_shutdown: ShutdownFn):
    """Build a FastAPI lifespan context manager from sync/async hooks."""

    @asynccontextmanager
    async def _lifespan(_app: Any) -> AsyncIterator[None]:
        started = on_startup()
        if hasattr(started, "__await__"):
            await started
        try:
            yield
        finally:
            ended = on_shutdown()
            if hasattr(ended, "__await__"):
                await ended

    return _lifespan


def json_response(body: dict[str, Any], *, status_code: int = 200) -> Response:
    return Response(content=json.dumps(body), status_code=status_code, media_type="application/json")


def error_envelope(*, code: str, message: str, status_code: int = 400) -> Response:
    return json_response({"ok": False, "error": {"code": code, "message": message}}, status_code=status_code)
