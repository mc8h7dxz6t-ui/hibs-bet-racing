"""UI shell helpers — mirror of hibs-bet ui_shell for racing parity."""

from __future__ import annotations

import os
from typing import Any


def ui_asset_version() -> str:
    raw = (os.getenv("HIBS_UI_ASSET_VERSION") or "").strip()
    if raw:
        return raw
    return "20260721a"


def static_v(filename: str, **kwargs: Any) -> str:
    from flask import url_for

    return url_for("static", filename=filename, v=ui_asset_version(), **kwargs)


def ui_shell_context() -> dict[str, Any]:
    return {
        "hibs_ui_asset_version": ui_asset_version(),
        "static_v": static_v,
        "hibs_theme_lite": True,
    }
