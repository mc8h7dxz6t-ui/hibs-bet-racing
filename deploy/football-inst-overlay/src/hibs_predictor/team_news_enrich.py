"""Team news / injury availability helpers (Phase 1 — fixture_injuries only)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

# API-Football injury `type` values (case-insensitive).
_ABSENCE_WEIGHTS = {
    "missing": 1.0,
    "injury": 1.0,
    "suspended": 1.0,
    "ineligible": 0.9,
    "doubtful": 0.45,
}


def _norm_team_key(name: str) -> str:
    s = unicodedata.normalize("NFKD", (name or "").strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def _injury_side(
    row: Dict[str, Any],
    *,
    home_name: str,
    away_name: str,
    home_id: Optional[int],
    away_id: Optional[int],
) -> Optional[str]:
    """Return 'home', 'away', or None if side cannot be resolved."""
    team = row.get("team") or {}
    tid = team.get("id")
    if home_id and tid and int(tid) == int(home_id):
        return "home"
    if away_id and tid and int(tid) == int(away_id):
        return "away"
    tname = str(team.get("name") or "")
    if not tname:
        return None
    key = _norm_team_key(tname)
    hk, ak = _norm_team_key(home_name), _norm_team_key(away_name)
    if key and hk and (key == hk or key in hk or hk in key):
        return "home"
    if key and ak and (key == ak or key in ak or ak in key):
        return "away"
    return None


def _row_penalty(row: Dict[str, Any]) -> float:
    raw = str(row.get("type") or row.get("reason") or "").strip().lower()
    for label, weight in _ABSENCE_WEIGHTS.items():
        if label in raw:
            return weight
    if raw:
        return 0.35
    return 0.25


def compute_attack_availability(
    injuries: List[Dict[str, Any]],
    *,
    home_name: str,
    away_name: str,
    home_id: Optional[int] = None,
    away_id: Optional[int] = None,
    max_penalty: float = 0.22,
) -> Tuple[float, float, Dict[str, Any]]:
    """
    Attack availability in (0.5, 1.0] per side from fixture injury rows.

    Each absence adds a capped penalty; doubtful counts at half weight vs missing.
    """
    home_pen = 0.0
    away_pen = 0.0
    home_n = away_n = 0
    for row in injuries or []:
        if not isinstance(row, dict):
            continue
        side = _injury_side(
            row,
            home_name=home_name,
            away_name=away_name,
            home_id=home_id,
            away_id=away_id,
        )
        if side is None:
            continue
        pen = _row_penalty(row)
        if side == "home":
            home_pen += pen
            home_n += 1
        else:
            away_pen += pen
            away_n += 1
    home_pen = min(max_penalty, home_pen)
    away_pen = min(max_penalty, away_pen)
    home_avail = max(0.5, 1.0 - home_pen)
    away_avail = max(0.5, 1.0 - away_pen)
    meta = {
        "home_absences": home_n,
        "away_absences": away_n,
        "home_penalty": round(home_pen, 3),
        "away_penalty": round(away_pen, 3),
    }
    return round(home_avail, 3), round(away_avail, 3), meta


def _norm_player_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", (name or "").strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _injury_player_names_for_side(
    injuries: List[Dict[str, Any]],
    *,
    side: str,
    home_name: str,
    away_name: str,
    home_id: Optional[int],
    away_id: Optional[int],
) -> set[str]:
    """Normalized player names on the injury feed for one side."""
    names: set[str] = set()
    for row in injuries or []:
        if not isinstance(row, dict):
            continue
        if _injury_side(
            row,
            home_name=home_name,
            away_name=away_name,
            home_id=home_id,
            away_id=away_id,
        ) != side:
            continue
        pl = row.get("player") or {}
        raw = str(pl.get("name") or "").strip()
        key = _norm_player_name(raw)
        if key:
            names.add(key)
    return names


def top_scorers_listed_absent(
    top_scorers: List[Dict[str, Any]],
    injuries: List[Dict[str, Any]],
    *,
    side: str,
    home_name: str,
    away_name: str,
    home_id: Optional[int] = None,
    away_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Top scorers whose names also appear on the API injury feed for this side.

    Display-only cross-reference — no invented importance weights.
    """
    absent_names = _injury_player_names_for_side(
        injuries,
        side=side,
        home_name=home_name,
        away_name=away_name,
        home_id=home_id,
        away_id=away_id,
    )
    if not absent_names or not top_scorers:
        return []
    out: List[Dict[str, Any]] = []
    for row in top_scorers:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        if _norm_player_name(name) in absent_names:
            out.append({"name": name, "goals": row.get("goals")})
    return out


def _fpl_hints_to_injury_rows(
    hints: List[Dict[str, Any]],
    *,
    team_name: str,
) -> List[Dict[str, Any]]:
    """Map FPL availability scraper rows into fixture_injuries shape."""
    out: List[Dict[str, Any]] = []
    for hint in hints or []:
        if not isinstance(hint, dict):
            continue
        player = str(hint.get("player") or "").strip()
        if not player:
            continue
        chance = hint.get("chance_pct")
        try:
            pct = float(chance) if chance is not None else 50.0
        except (TypeError, ValueError):
            pct = 50.0
        injury_type = "doubtful" if pct >= 50 else "missing"
        out.append(
            {
                "team": {"name": team_name},
                "player": {"name": player},
                "type": injury_type,
                "reason": hint.get("news") or "fpl_availability",
                "source": "fpl_availability",
            }
        )
    return out


def _injuries_for_fixture(enriched: Dict[str, Any]) -> List[Dict[str, Any]]:
    """API injuries first; ``injury_hint`` ladder (FPL) when API list empty."""
    injuries = enriched.get("fixture_injuries") or []
    if not isinstance(injuries, list):
        injuries = []
    if injuries:
        return injuries
    supplemental = enriched.get("supplemental") or {}
    hints = supplemental.get("fpl_injury_hints")
    if not isinstance(hints, dict):
        return injuries
    home_name = str(enriched.get("home") or "")
    away_name = str(enriched.get("away") or "")
    merged = list(injuries)
    merged.extend(_fpl_hints_to_injury_rows(hints.get("home") or [], team_name=home_name))
    merged.extend(_fpl_hints_to_injury_rows(hints.get("away") or [], team_name=away_name))
    if merged:
        enriched["injury_hint_source"] = "fpl_availability"
    return merged


def apply_team_news_fields(enriched: Dict[str, Any]) -> Dict[str, Any]:
    """Set attack_availability_* on an enriched fixture row."""
    injuries = _injuries_for_fixture(enriched)
    home_name = str(enriched.get("home") or "")
    away_name = str(enriched.get("away") or "")
    home_id = enriched.get("home_id")
    away_id = enriched.get("away_id")
    home_avail, away_avail, meta = compute_attack_availability(
        injuries,
        home_name=home_name,
        away_name=away_name,
        home_id=home_id,
        away_id=away_id,
    )
    enriched["attack_availability_home"] = home_avail
    enriched["attack_availability_away"] = away_avail
    enriched["team_news_meta"] = meta
    home_scorers = enriched.get("home_top_scorers") or []
    away_scorers = enriched.get("away_top_scorers") or []
    if isinstance(home_scorers, list) and home_scorers:
        meta["home_scorers_absent"] = top_scorers_listed_absent(
            home_scorers,
            injuries,
            side="home",
            home_name=home_name,
            away_name=away_name,
            home_id=home_id,
            away_id=away_id,
        )
    if isinstance(away_scorers, list) and away_scorers:
        meta["away_scorers_absent"] = top_scorers_listed_absent(
            away_scorers,
            injuries,
            side="away",
            home_name=home_name,
            away_name=away_name,
            home_id=home_id,
            away_id=away_id,
        )
    enriched["team_news_meta"] = meta
    return enriched
