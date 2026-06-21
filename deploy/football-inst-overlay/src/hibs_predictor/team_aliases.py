"""Shared team-name normalization for odds matching, tables, and live scores."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# Display-name aliases → canonical token (lowercase, no accents).
TEAM_CANONICAL_ALIASES: dict[str, str] = {
    # UK (existing)
    "hibs": "hibernian",
    "man utd": "manchester united",
    "man city": "manchester city",
    "spurs": "tottenham",
    "wolves": "wolverhampton",
    "nottm forest": "nottingham forest",
    # European naming (API-Sports / audit log vs FotMob / ESPN / FPL)
    "psg": "paris saint germain",
    "paris sg": "paris saint germain",
    "kaa gent": "gent",
    "krc genk": "genk",
    "tottenham hotspur": "tottenham",
    "nott'm forest": "nottingham forest",
    # League of Ireland — API-Football vs The Odds API naming
    "st patricks athletic": "st patricks athletic",
    "st patrick's athletic": "st patricks athletic",
    "st. patrick's athletic": "st patricks athletic",
    "saint patricks athletic": "st patricks athletic",
    "st patricks": "st patricks athletic",
    "bohemian fc": "bohemians",
    "bohemians dublin": "bohemians",
    "shamrock rovers fc": "shamrock rovers",
    "derry city fc": "derry city",
    "dundalk fc": "dundalk",
    "cork city fc": "cork city",
    "galway united fc": "galway united",
    "waterford fc": "waterford",
    "drogheda united fc": "drogheda united",
    "sligo rovers fc": "sligo rovers",
    "shelbourne fc": "shelbourne",
    "bray wanderers fc": "bray wanderers",
    "ucd fc": "ucd",
    "university college dublin": "ucd",
    "finn harps fc": "finn harps",
    "longford town fc": "longford town",
    "treaty united fc": "treaty united",
    "wexford fc": "wexford",
    "kerry fc": "kerry",
    "athlone town fc": "athlone town",
    "cobh ramblers fc": "cobh ramblers",
}


def team_key(name: Any) -> str:
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    for suffix in (" fc", " afc", " cf", " sc", " united", " city", " town", " rovers"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


def canonical_team_key(name: Any) -> str:
    key = team_key(name)
    return TEAM_CANONICAL_ALIASES.get(key, key)


def team_names_match(a: str, b: str) -> bool:
    """Loose match across bookmakers and API providers (incl. LOI naming)."""
    if not a or not b:
        return False
    ca, cb = canonical_team_key(a), canonical_team_key(b)
    if ca == cb:
        return True
    if ca in cb or cb in ca:
        return True
    ap = ca.split()
    bp = cb.split()
    if ap and bp and ap[0] == bp[0] and len(ap[0]) > 3:
        return True
    na, nb = team_key(a), team_key(b)
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    for prefix in ("sc ", "fc ", "ac ", "as ", "sv ", "sk ", "rc ", "cd ", "cf ", "st "):
        if na.startswith(prefix):
            core = na[len(prefix) :].strip()
            if core and (core == nb or core in nb or nb in core):
                return True
        if nb.startswith(prefix):
            core = nb[len(prefix) :].strip()
            if core and (core == na or core in na or na in core):
                return True
    return False
