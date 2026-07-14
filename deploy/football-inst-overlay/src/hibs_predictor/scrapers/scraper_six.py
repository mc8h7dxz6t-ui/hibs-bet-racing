"""Production six-source enrichment plan for 85%+ fixture data quality.

The six slots maximise unique signals without VPS meltdown. Five are HTML/JSON
scrapes or open data; slot six is API ``fixtures/statistics`` measured xG (SofaScore
is optional overflow when reachable — often HTTP 403).

See ``docs/SCRAPER_SIX_PLAN.md`` for budget, deferrals, and league notes.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# id, label, kind, env_enable, env_disable, supplemental_keys, dq_notes
SCRAPER_SIX: List[Dict[str, Any]] = [
    {
        "id": "api_football",
        "label": "API-Football (core)",
        "kind": "api",
        "env_enable": [],
        "env_disable": ["HIBS_DISABLE_API_SPORTS"],
        "supplemental_keys": ("api_squad_depth",),
        "dq_blocks": ("team_ids", "fixture_id", "recent_home", "recent_away", "stats_home", "stats_away", "stand_home", "stand_away", "book_1x2", "injuries"),
        "api_budget": "Primary quota; HIBS_API_SPORTS_HOURLY_LIMIT (default 400/h VPS)",
        "rate_limit": "Client-side sem HIBS_ENRICH_API_SEM; 12–24h cache on heavy endpoints",
    },
    {
        "id": "api_statistics_xg",
        "label": "API-Football fixtures/statistics xG",
        "kind": "api",
        "env_enable": ["HIBS_FETCH_FIXTURE_STATISTICS_XG"],
        "env_disable": [],
        "supplemental_keys": ("api_statistics_xg",),
        "dq_blocks": ("xg",),
        "dq_xg_pts": 18,
        "api_budget": "HIBS_FETCH_FIXTURE_STATISTICS_XG_MAX per dashboard refresh (default 24); 12h cache",
        "rate_limit": "Budget gate in fixture_statistics_xg; skipped when fixture xG already measured",
    },
    {
        "id": "fotmob_xg",
        "label": "FotMob league-table xG",
        "kind": "scrape",
        "env_enable": ["HIBS_ENABLE_FOTMOB_XG", "HIBS_MAX_DATA"],
        "env_disable": [],
        "supplemental_keys": ("fotmob_xg", "fotmob_league_supported"),
        "dq_blocks": ("xg", "supplemental"),
        "dq_xg_pts": "13–14 (fotmob_league_xg tier)",
        "api_budget": "0 API calls — public JSON",
        "rate_limit": "6h supplemental cache; league table cached per league",
    },
    {
        "id": "understat",
        "label": "Understat xG",
        "kind": "scrape",
        "env_enable": ["HIBS_ENABLE_UNDERSTAT_LIGHT", "HIBS_SCRAPE_XG"],
        "env_disable": ["HIBS_ENABLE_HEAVY_SCRAPERS"],
        "supplemental_keys": ("understat_light", "understat"),
        "dq_blocks": ("xg", "supplemental"),
        "dq_xg_pts": "14–16 (understat_xg / understat_team_xg)",
        "api_budget": "0 API calls — low-rate AJAX",
        "rate_limit": "Light always; full league page when heavy scrapers on; 6h supplemental cache",
    },
    {
        "id": "soccerstats",
        "label": "SoccerStats standings",
        "kind": "scrape",
        "env_enable": ["HIBS_PREFER_SCRAPED_STANDINGS"],
        "env_disable": [],
        "supplemental_keys": ("soccerstats_positions", "soccerstats_table_rows"),
        "dq_blocks": ("stand_home", "stand_away", "supplemental"),
        "dq_xg_pts": None,
        "api_budget": "0 API calls — one HTML table per league per cache window",
        "rate_limit": "Table fetch cached; Norway/Finland/Scotland L1–L2 + EPL sample health probe",
    },
    {
        "id": "statsbomb",
        "label": "StatsBomb open (cups proxy)",
        "kind": "open_data",
        "env_enable": ["HIBS_ENABLE_STATSBOMB_LIGHT", "HIBS_MAX_DATA"],
        "env_disable": ["HIBS_ENABLE_STATSBOMB_OPEN_MATCHES"],
        "supplemental_keys": ("statsbomb_open_team_proxy", "statsbomb_competition_count"),
        "dq_blocks": ("xg", "supplemental"),
        "dq_xg_pts": "11 (statsbomb_goals_proxy_xg — not measured; never 18)",
        "api_budget": "0 API calls — GitHub raw JSON",
        "rate_limit": "Cups default-on; domestic when STATSBOMB_LIGHT or MAX_DATA",
    },
]

# Optional overflow — not counted toward the six
SCRAPER_SIX_OVERFLOW: Dict[str, Any] = {
    "id": "sofascore",
    "label": "Sofascore rolling xG",
    "env_enable": ["HIBS_ENABLE_SOFASCORE_XG", "HIBS_MAX_DATA"],
    "status": "blocked",
    "notes": "HTTP 403 common; HIBS_ENABLE_SOFASCORE_XG=1 when reachable. DQ xG tier 13.5.",
}

TARGETED_OVERFLOW: List[Dict[str, Any]] = [
    {
        "id": "espn_scoreboard",
        "label": "ESPN scoreboard",
        "env_enable": ["HIBS_SETTLE_BACKUP_ESPN", "HIBS_ENABLE_ESPN_FIXTURES"],
        "status": "wired",
        "notes": "FT settlement + fixture fallback (WC/UCL) when FDO/FotMob empty; no API key.",
    },
    {
        "id": "fpl_api",
        "label": "Fantasy Premier League API",
        "env_enable": ["HIBS_ENABLE_FPL_EPL", "HIBS_MAX_DATA"],
        "status": "wired",
        "notes": "EPL xG, table, recent fixtures, injury hints.",
    },
    SCRAPER_SIX_OVERFLOW,
]

DEFERRED_PLANNED: List[Dict[str, str]] = [
    {"id": "footystats", "reason": "Paginated/login walls; no stable public JSON API"},
    {"id": "datamb", "reason": "Chart-heavy SPA; brittle without licensed feed"},
    {"id": "uefa", "reason": "No documented public API; UEFA via API-Football/FDO mappings"},
    {"id": "footballdata_io", "reason": "Endpoint/auth not verified (distinct from football-data.org)"},
    {"id": "soccerdata", "reason": "pip fallback only if custom parsers break"},
    {"id": "worldfootballr", "reason": "R toolchain; poor fit for Python app"},
    {"id": "transfermarkt", "reason": "ToS; injuries/squad via API-Football instead"},
    {"id": "xgstat", "reason": "No public JSON API"},
    {"id": "besoccer", "reason": "No documented JSON feed"},
]


def _env_on(name: str, default: str = "1") -> bool:
    return (os.getenv(name, default) or default).strip().lower() not in ("0", "false", "no", "off")


def scraper_six_enabled(source_id: str) -> bool:
    """True when env flags allow this six-plan source (best-effort)."""
    row = next((s for s in SCRAPER_SIX if s["id"] == source_id), None)
    if not row:
        return False
    for off in row.get("env_disable") or ():
        if _env_on(off, "0"):
            return False
    enables = row.get("env_enable") or ()
    if not enables:
        return True
    if source_id == "fotmob_xg":
        from hibs_predictor.scrapers import fotmob_client as fm

        return any(_env_on(e, "0" if e == "HIBS_MAX_DATA" else "1") for e in enables) or fm.fotmob_xg_enabled("")
    if source_id == "statsbomb":
        raw = os.getenv("HIBS_ENABLE_STATSBOMB_OPEN_MATCHES", "").strip().lower()
        if raw in ("0", "false", "no", "off"):
            return False
        if any(_env_on(e, "0" if e == "HIBS_MAX_DATA" else "1") for e in enables):
            return True
        return False
    if source_id == "api_statistics_xg":
        from hibs_predictor.fixture_statistics_xg import fixture_statistics_xg_enabled

        return fixture_statistics_xg_enabled()
    if source_id == "understat":
        if not _env_on("HIBS_ENABLE_UNDERSTAT_LIGHT", "1"):
            return False
        return _env_on("HIBS_ENABLE_HEAVY_SCRAPERS", "1") or True
    return any(_env_on(e, "1") for e in enables)


def _source_hit(source: Dict[str, Any], sup: Dict[str, Any], enriched: Dict[str, Any]) -> bool:
    sid = source["id"]
    if sid == "api_football":
        hid = (enriched.get("teams") or {}).get("home", {}).get("id") or enriched.get("home_id")
        aid = (enriched.get("teams") or {}).get("away", {}).get("id") or enriched.get("away_id")
        return bool(hid and aid)
    if sid == "api_statistics_xg":
        if sup.get("api_statistics_xg"):
            return True
        return str(enriched.get("xg_source") or "").lower() == "api_statistics_xg"
    for key in source.get("supplemental_keys") or ():
        val = sup.get(key)
        if val is None or val == "" or val == [] or val == {}:
            continue
        if key.endswith("_error") or key == "heavy_skipped":
            continue
        if key == "fotmob_league_supported" and not sup.get("fotmob_xg"):
            continue
        if key == "statsbomb_competition_count" and not sup.get("statsbomb_open_team_proxy"):
            continue
        return True
    return False


def annotate_scraper_six(
    sup: Dict[str, Any],
    enriched: Dict[str, Any],
    league_code: str = "",
) -> None:
    """Mutate supplemental with six-plan status + mirror API statistics xG for DQ context."""
    xg_src = str(enriched.get("xg_source") or "").lower()
    if xg_src == "api_statistics_xg" and not sup.get("api_statistics_xg"):
        try:
            sup["api_statistics_xg"] = {
                "xg_home": round(float(enriched.get("xg_home") or 0), 3),
                "xg_away": round(float(enriched.get("xg_away") or 0), 3),
            }
        except (TypeError, ValueError):
            pass

    status: Dict[str, Any] = {}
    hits = 0
    misses = sup.get("supplemental_misses") if isinstance(sup.get("supplemental_misses"), dict) else {}
    for src in SCRAPER_SIX:
        enabled = scraper_six_enabled(src["id"])
        hit = _source_hit(src, sup, enriched)
        if hit and enabled:
            hits += 1
        row: Dict[str, Any] = {
            "enabled": enabled,
            "hit": hit,
            "label": src["label"],
        }
        if not hit and enabled and src["id"] != "api_football":
            for mk in src.get("supplemental_keys") or ():
                if mk in misses:
                    row["miss"] = misses[mk]
                    break
        status[src["id"]] = row

    sup["scraper_six"] = {
        "hits": hits,
        "enabled_count": sum(1 for s in SCRAPER_SIX if scraper_six_enabled(s["id"])),
        "sources": status,
        "league_code": league_code or None,
    }


def scraper_six_plan_summary() -> Dict[str, Any]:
    """Static plan metadata for docs / health UI."""
    return {
        "six": [{"id": s["id"], "label": s["label"], "kind": s["kind"]} for s in SCRAPER_SIX],
        "overflow": SCRAPER_SIX_OVERFLOW,
        "targeted_overflow": TARGETED_OVERFLOW,
        "deferred": DEFERRED_PLANNED,
        "target_dq_pct": 85,
        "vps_profile": "deploy/apply-vps-safe-production.sh (MAX_DATA, statistics xG, FotMob, FBref blocked)",
    }
