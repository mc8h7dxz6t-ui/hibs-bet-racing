"""Catalog of public / scrape-style football data sources (planning + honesty).

Many sites below prohibit or discourage bulk scraping in their terms of use.
Anything marked ``wired`` is already used (best-effort, rate-limited) from
``collect_supplemental`` or related modules. ``experimental`` may exist only as
a stub or optional Playwright probe. ``planned`` is not implemented — treat as
product backlog, not a promise of extraction quality. ``blocked`` / ``deferred``
are honest non-wired states for the status UI.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Keys: id (stable), label, focus (one line), status, module (optional), notes
SOURCE_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "api_sports",
        "label": "API-Football/API-Sports",
        "focus": "Fixtures, standings, team stats, recent form, injuries, odds and selected fixture statistics",
        "status": "wired",
        "module": "hibs_predictor.api_clients.ApiSportsFootballClient",
        "notes": "Documented API-Football endpoints; standings try current then previous season for completed/thin windows. Squad depth via ``players/squads`` when ``HIBS_ENABLE_API_SQUAD_DEPTH=1``.",
    },
    {
        "id": "football_data_org",
        "label": "Football-Data.org",
        "focus": "Documented fixtures and standings for supported competitions",
        "status": "wired",
        "module": "hibs_predictor.api_clients.FootballDataOrgClient",
        "notes": "Official v4 API; used for fixture fallback and league-table/position fallback, including previous-season tables when current fixture windows are thin.",
    },
    {
        "id": "fotmob",
        "label": "FotMob",
        "focus": "Public daily match JSON; league-table team xG for UEFA cups + optional domestic fallback",
        "status": "wired",
        "module": "hibs_predictor.scrapers.fotmob_client",
        "notes": "``/api/data/matches`` fixture fallback; ``/api/data/leagues`` season xG table. ``HIBS_ENABLE_FOTMOB_XG`` / cups default-on.",
    },
    {
        "id": "espn_scoreboard",
        "label": "ESPN scoreboard",
        "focus": "Public JSON scoreboards for cups and domestic leagues (FT settlement backup)",
        "status": "wired",
        "module": "hibs_predictor.scrapers.espn_client",
        "notes": "``site.api.espn.com``; ``HIBS_SETTLE_BACKUP_ESPN=1`` (default). Strong for WC/UCL when FotMob lags.",
    },
    {
        "id": "fpl_api",
        "label": "Fantasy Premier League API",
        "focus": "EPL season xG, table, recent fixtures, injury availability hints",
        "status": "wired",
        "module": "hibs_predictor.scrapers.fpl_client",
        "notes": "``fantasy.premierleague.com/api``; ``HIBS_ENABLE_FPL_EPL=1`` or ``HIBS_MAX_DATA=1``. EPL only.",
    },
    {
        "id": "fbref",
        "label": "FBref",
        "focus": "Deep squad tables, advanced metrics, Opta-backed stats on many leagues",
        "status": "wired",
        "module": "hibs_predictor.scrapers.fbref_client",
        "notes": "HTML tables; follow Sports Reference robots; heavy path in collect_supplemental. May 403 from datacenter IPs — set HIBS_FBREF_BLOCKED=1 on VPS; curl_cffi rarely fixes datacenter blocks.",
    },
    {
        "id": "understat",
        "label": "Understat",
        "focus": "Shot-level xG and league JSON embedded in public pages",
        "status": "wired",
        "module": "hibs_predictor.scrapers.understat_client",
        "notes": "Light + heavy modes via /getLeagueData AJAX (session cookie); limited league set; respect low request rate.",
    },
    {
        "id": "sofascore",
        "label": "Sofascore",
        "focus": "Live + historical team feeds, ratings-style summaries",
        "status": "blocked",
        "module": "hibs_predictor.scrapers.sofascore_client",
        "notes": "Often HTTP 403 from server/datacenter IPs — optional rolling xG only when reachable.",
    },
    {
        "id": "statsbomb_open",
        "label": "StatsBomb Open Data",
        "focus": "Free competition + match JSON (goals proxy, not full xG pipeline)",
        "status": "wired",
        "module": "hibs_predictor.scrapers.statsbomb_open",
        "notes": "UCL/Europa/Euros/World Cup + domestic leagues; cup leagues default-on for goals proxy.",
    },
    {
        "id": "whoscored",
        "label": "WhoScored",
        "focus": "Rich match analytics, event streams, ratings (mostly behind JS)",
        "status": "experimental",
        "module": "hibs_predictor.scrapers.whoscored_client",
        "notes": "Optional Playwright fetch test only; no production feature pipeline — ToS + stability.",
    },
    {
        "id": "uefa",
        "label": "UEFA",
        "focus": "Official UEFA competition pages / feeds for club and international tournaments",
        "status": "planned",
        "module": None,
        "notes": "No stable documented public API confirmed; current UEFA coverage comes through Football-Data.org/API-Football competition mappings.",
    },
    {
        "id": "footballdata_io",
        "label": "footballdata.io",
        "focus": "Potential fixture/stat feed distinct from football-data.org",
        "status": "planned",
        "module": None,
        "notes": "Not integrated until a documented endpoint, auth model, and terms are verified.",
    },
    {
        "id": "xgstat",
        "label": "xGStat",
        "focus": "xG/team-stat enrichment",
        "status": "deferred",
        "module": "hibs_predictor.scrapers.xgstat_client",
        "notes": "Probe-only: no stable public JSON API found; xG covered by Understat/FotMob/API chain.",
    },
    {
        "id": "besoccer",
        "label": "BeSoccer",
        "focus": "Fixtures, tables, team/news pages",
        "status": "deferred",
        "module": "hibs_predictor.scrapers.besoccer_client",
        "notes": "Probe-only: site reachable but no documented public JSON feed; use SoccerStats/API-FotMob instead.",
    },
    {
        "id": "transfermarkt",
        "label": "Transfermarkt",
        "focus": "Transfers, market values, injuries, squad depth",
        "status": "deferred",
        "module": "hibs_predictor.scrapers.transfermarkt_client",
        "notes": "Robots probe only; production injuries + squad via API-Football (not Transfermarkt HTML).",
    },
    {
        "id": "footystats",
        "label": "FootyStats",
        "focus": "League/team totals, O/U, corners, clean sheets style aggregates",
        "status": "planned",
        "module": None,
        "notes": "Often paginated + login walls; evaluate official export/API if any.",
    },
    {
        "id": "soccerstats",
        "label": "SoccerStats",
        "focus": "League table standings when API positions are missing",
        "status": "wired",
        "module": "hibs_predictor.scrapers.soccerstats_standings",
        "notes": "HTML tables.asp fallback after API/FDO; Norway/Finland/Scotland L1-L2.",
    },
    {
        "id": "datamb",
        "label": "DataMB",
        "focus": "Wide league coverage, visual-heavy metrics",
        "status": "planned",
        "module": None,
        "notes": "Chart-heavy sites are brittle for scrapers; prefer licensed feeds if available.",
    },
    {
        "id": "soccerdata",
        "label": "soccerdata (Python)",
        "focus": "Unified FBref / WhoScored / Understat → DataFrames",
        "status": "planned",
        "module": None,
        "notes": "Optional pip fallback behind flag if custom parsers break; not enabled by default.",
    },
    {
        "id": "worldfootballr",
        "label": "worldfootballR",
        "focus": "FBref deep stats via R (+ immature Python wrapper)",
        "status": "planned",
        "module": None,
        "notes": "R-first toolchain; poor fit for this Python app unless exposed as a sidecar service.",
    },
]


def sources_by_status(status: str) -> List[Dict[str, Any]]:
    """Return catalog rows matching status: wired | experimental | planned | blocked | deferred."""
    s = status.strip().lower()
    return [row for row in SOURCE_CATALOG if str(row.get("status", "")).lower() == s]
