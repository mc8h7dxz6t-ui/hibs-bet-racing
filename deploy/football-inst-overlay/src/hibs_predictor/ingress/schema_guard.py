"""Fail-closed ingress validation — semver contract + structural null rejection."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+].*)?$")


class IngressRejectError(ValueError):
    """Payload rejected at ingress boundary — do not parse or persist."""


def parse_semver(raw: str) -> tuple[int, int, int]:
    text = (raw or "").strip()
    m = _SEMVER_RE.match(text)
    if not m:
        raise IngressRejectError(f"invalid semver: {raw!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def semver_compatible(
    payload_version: str,
    *,
    min_version: str,
    max_version: Optional[str] = None,
) -> bool:
    got = parse_semver(payload_version)
    lo = parse_semver(min_version)
    if got < lo:
        return False
    if max_version:
        hi = parse_semver(max_version)
        if got > hi:
            return False
    return True


def _is_nullish(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def reject_structural_nulls(
    obj: Any,
    required_paths: Sequence[str],
    *,
    prefix: str = "",
) -> None:
    """Reject when any dotted path is null/empty on a mapping tree."""
    for path in required_paths:
        cur: Any = obj
        for part in path.split("."):
            if not isinstance(cur, Mapping):
                raise IngressRejectError(f"structural null at {prefix}{path}")
            cur = cur.get(part)
        if _is_nullish(cur):
            raise IngressRejectError(f"structural null at {prefix}{path}")


def validate_ingress_payload(
    payload: Mapping[str, Any],
    *,
    schema_version_key: str = "schema_version",
    expected_min: str,
    expected_max: Optional[str] = None,
    required_paths: Iterable[str] = (),
) -> str:
    """
    Fail-closed gate. Returns accepted schema version string.
    Raises IngressRejectError on semver mismatch or structural nulls.
    """
    if not isinstance(payload, Mapping):
        raise IngressRejectError("payload must be a mapping")
    version = str(payload.get(schema_version_key) or "").strip()
    if not version:
        raise IngressRejectError(f"missing {schema_version_key}")
    if not semver_compatible(version, min_version=expected_min, max_version=expected_max):
        raise IngressRejectError(
            f"semver {version} outside [{expected_min}, {expected_max or '∞'}]"
        )
    reject_structural_nulls(payload, list(required_paths))
    return version
