"""Shared course-name aliases for exchange odds matching (Matchbook, Betfair, etc.)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from hibs_racing.entity.natural_key import courses_match, normalize_course

# Canonical slug → substrings to match in exchange event / venue labels.
COURSE_ALIASES: dict[str, list[str]] = {
    "newton_abbot": ["newton abbot", "newton-abbot"],
    "stratford": ["stratford-on-avon", "stratford on avon", "stratford"],
    "fontwell": ["fontwell park", "fontwell"],
    "leopardstown": ["leopardstown (ire)", "leopardstown"],
    "newcastle": ["newcastle (aw)", "newcastle aw", "newcastle"],
    "kempton": ["kempton park", "kempton (aw)", "kempton"],
    "lingfield": ["lingfield park", "lingfield (aw)", "lingfield"],
    "wolverhampton": ["wolverhampton (aw)", "wolverhampton"],
    "southwell": ["southwell (aw)", "southwell"],
    "chelmsford": ["chelmsford city", "chelmsford (aw)", "chelmsford"],
    "brighton": ["brighton", "brighton & hove", "brighton and hove"],
    "great_yarmouth": ["great yarmouth", "yarmouth"],
    "hamilton": ["hamilton park", "hamilton"],
    "ayr": ["ayr", "ayr (scot)"],
    "perth": ["perth", "perth (scot)"],
    "downpatrick": ["downpatrick", "downpatrick (ni)"],
    "down_royal": ["down royal", "down royal (ni)"],
    "curragh": ["curragh", "curragh (ire)"],
    "galway": ["galway", "galway (ire)"],
    "punchestown": ["punchestown", "punchestown (ire)"],
    "naas": ["naas", "naas (ire)"],
    "tipperary": ["tipperary", "tipperary (ire)"],
    "wexford": ["wexford", "wexford (ire)"],
    "killarney": ["killarney", "killarney (ire)"],
    "roscommon": ["roscommon", "roscommon (ire)"],
    "sligo": ["sligo", "sligo (ire)"],
    "listowel": ["listowel", "listowel (ire)"],
    "bath": ["bath"],
    "salisbury": ["salisbury"],
    "goodwood": ["goodwood"],
    "york": ["york"],
    "doncaster": ["doncaster"],
    "ascot": ["ascot", "royal ascot"],
    "epsom": ["epsom", "epsom downs"],
    "sandown": ["sandown", "sandown park"],
    "kempton_park": ["kempton park", "kempton"],
}


def merge_course_aliases(extra: dict[str, list[str]] | None) -> None:
    """Merge slug → alias lists into the global COURSE_ALIASES table."""
    if not extra:
        return
    for slug, tokens in extra.items():
        key = normalize_course(slug) or str(slug).strip().lower().replace(" ", "_")
        if not key:
            continue
        existing = list(COURSE_ALIASES.get(key, []))
        for token in tokens or []:
            text = str(token).strip().lower()
            if text and text not in existing:
                existing.append(text)
        COURSE_ALIASES[key] = existing


def load_course_aliases_file(path: str | Path | None) -> None:
    """Load optional YAML/JSON course alias overrides (operator-maintained mapping file)."""
    if not path:
        return
    p = Path(path).expanduser()
    if not p.is_file():
        return
    raw = p.read_text(encoding="utf-8")
    data: Any
    if p.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(raw) or {}
    else:
        data = json.loads(raw)
    if isinstance(data, dict):
        merge_course_aliases({str(k): list(v) if isinstance(v, (list, tuple)) else [v] for k, v in data.items()})


def resolve_course_aliases(cfg: dict | None = None) -> None:
    """Load aliases from env + config once per odds fetch."""
    path = os.environ.get("HIBS_COURSE_ALIASES_FILE", "").strip()
    if not path and cfg:
        for section in ("betfair", "matchbook", "exchange"):
            path = str((cfg.get(section) or {}).get("course_aliases_file") or "").strip()
            if path:
                break
        inline = (cfg.get("betfair") or {}).get("course_aliases") or (cfg.get("matchbook") or {}).get(
            "course_aliases"
        )
        if inline and isinstance(inline, dict):
            merge_course_aliases(inline)
    if path:
        load_course_aliases_file(path)


def course_alias_tokens(course: str | None) -> list[str]:
    if not course:
        return []
    slug = normalize_course(course)
    tokens = list(COURSE_ALIASES.get(slug, []))
    base = str(course).lower().split("(")[0].strip()
    tokens.extend([base, slug.replace("_", " ")])
    tokens.append(slug)
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        t = t.strip().lower()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def venue_matches(card_course: str | None, exchange_strings: list[str]) -> bool:
    if not card_course:
        return True
    aliases = course_alias_tokens(card_course)
    for exch in exchange_strings:
        if courses_match(card_course, exch):
            return True
        for alias in aliases:
            if alias in exch or exch in alias:
                return True
    return False
