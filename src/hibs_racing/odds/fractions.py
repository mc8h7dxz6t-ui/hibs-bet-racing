from __future__ import annotations

import re

_FRAC_RE = re.compile(r"^(\d+)\s*/\s*(\d+)$")


def fraction_to_decimal(text: object) -> float | None:
    if text is None:
        return None
    raw = str(text).strip().lower()
    if not raw or raw in {"-", "—", "sp", "nr"}:
        return None
    if raw in {"evs", "evens"}:
        return 2.0
    try:
        val = float(raw)
        return val if val > 1.0 else None
    except ValueError:
        pass
    m = _FRAC_RE.match(raw)
    if m:
        num, den = int(m.group(1)), int(m.group(2))
        if den <= 0:
            return None
        return round(num / den + 1.0, 3)
    return None
