"""CLI helpers — structured errors and JSON envelopes."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

from inst_spine.errors import InstError


def error_envelope(exc: InstError) -> dict[str, Any]:
    return {"ok": False, "error": exc.to_dict()}


def emit_error(exc: InstError) -> None:
    print(json.dumps(error_envelope(exc), indent=2), file=sys.stderr)


def run_cli(main: Callable[[], int]) -> None:
    """Wrap product CLI main — never leak raw tracebacks to buyers."""
    try:
        raise SystemExit(main())
    except InstError as exc:
        emit_error(exc)
        raise SystemExit(1) from exc
    except json.JSONDecodeError as exc:
        emit_error(InstError(code="INVALID_JSON", message=str(exc)))
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        raise SystemExit(130)
