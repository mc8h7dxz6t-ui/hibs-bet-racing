"""Typed Inst++ errors — structured CLI envelopes, fail-closed semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InstError(Exception):
    """Base institutional error with machine-readable code."""

    code: str
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            out["details"] = self.details
        return out


class IngestValidationError(InstError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(code="INGEST_VALIDATION", message=message, details=details)


class ExportAbortError(InstError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(code="EXPORT_ABORT", message=message, details=details)


class BundleVerifyError(InstError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(code="BUNDLE_VERIFY", message=message, details=details)


class UpstreamError(InstError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        details = {"upstream_status": status} if status is not None else None
        super().__init__(code="UPSTREAM_FAIL", message=message, details=details)


class RateLimitError(InstError):
    def __init__(self, message: str, *, retry_after_sec: float | None = None) -> None:
        details = {"retry_after_sec": retry_after_sec} if retry_after_sec is not None else None
        super().__init__(code="RATE_LIMIT", message=message, details=details)


class CoverageError(InstError):
    def __init__(self, message: str, *, coverage_pct: float | None = None) -> None:
        details = {"coverage_pct": coverage_pct} if coverage_pct is not None else None
        super().__init__(code="COVERAGE_FAIL", message=message, details=details)
