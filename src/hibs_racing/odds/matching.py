from __future__ import annotations

import re

_HORSE_SUFFIX_RE = re.compile(r"\s*\([A-Z]{2,3}\)\s*$", re.I)
_CLOTH_PREFIX_RE = re.compile(r"^\d+\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_horse_name(name: str | None) -> str:
    if not name:
        return ""
    text = str(name).strip().lower()
    text = _CLOTH_PREFIX_RE.sub("", text)
    text = _HORSE_SUFFIX_RE.sub("", text)
    return _NON_ALNUM_RE.sub("", text)


def horse_names_match(a: str | None, b: str | None) -> bool:
    na, nb = normalize_horse_name(a), normalize_horse_name(b)
    if not na or not nb:
        return False
    return na == nb or na.startswith(nb) or nb.startswith(na)
