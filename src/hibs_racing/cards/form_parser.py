from __future__ import annotations

import re

_POOR_RUN_RE = re.compile(r"(?:^|[^0-9])(?:PU|F|UR|BD|RO|RR|REF|SU|DSQ)(?:[^0-9]|$)", re.I)
_LTO_POS_RE = re.compile(r"(?:^|[-/])([0-9]+|[0-9]+/[0-9]+|[0-9]+st|[0-9]+nd|[0-9]+rd|[0-9]+th)", re.I)
_DIST_IN_FORM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*f", re.I)


def _parse_lto_position(form: str) -> int | None:
    """Leftmost recent finish in RP form string."""
    text = form.strip()
    if not text:
        return None
    if text.upper().startswith("F") and len(text) > 1 and text[1].isdigit():
        pass
    m = _LTO_POS_RE.search(text)
    if not m:
        return None
    token = m.group(1).lower().replace("st", "").replace("nd", "").replace("rd", "").replace("th", "")
    if "/" in token:
        token = token.split("/", 1)[0]
    try:
        pos = int(token)
        return pos if pos > 0 else None
    except ValueError:
        return None


def _form_flags(form: str) -> tuple[int, int]:
    upper = form.upper()
    cd = 1 if re.search(r"CD", upper) else 0
    bf = 1 if re.search(r"\bBF\b", upper) else 0
    return cd, bf


def _poor_runs_last_n(form: str, n: int = 3) -> int:
    parts = re.split(r"[-/]", form.strip())
    count = 0
    for part in parts[:n]:
        if _POOR_RUN_RE.search(part):
            count += 1
    return count


def _last_run_distance_f(form: str) -> float | None:
    m = _DIST_IN_FORM_RE.search(form)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def parse_form_string(
    form: object,
    *,
    today_distance_f: object = None,
) -> dict[str, float | int | None]:
    """
    Conservative parse of RP form string — unknown tokens ignored.
    Returns structured fields for enrich layer / optional ranker features.
    """
    if form is None or (isinstance(form, float) and str(form) == "nan"):
        text = ""
    else:
        text = str(form).strip()
    if not text:
        return {
            "form_lto_position": None,
            "form_trip_change_f": None,
            "form_cd_flag": 0,
            "form_bf_flag": 0,
            "form_poor_runs_3": 0,
        }
    cd, bf = _form_flags(text)
    lto_dist = _last_run_distance_f(text)
    trip_change = None
    if lto_dist is not None and today_distance_f is not None:
        try:
            trip_change = float(today_distance_f) - lto_dist
        except (TypeError, ValueError):
            trip_change = None
    return {
        "form_lto_position": _parse_lto_position(text),
        "form_trip_change_f": trip_change,
        "form_cd_flag": cd,
        "form_bf_flag": bf,
        "form_poor_runs_3": _poor_runs_last_n(text, 3),
    }
