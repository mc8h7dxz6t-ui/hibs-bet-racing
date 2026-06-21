"""Scrape-first rescue when API enrichment leaves fixtures thin (form, table, positions).

Runs after supplemental merge so SoccerStats / FotMob / StatsBomb proxies can fill gaps
without blocking the primary API path. Gated by ``HIBS_THIN_DATA_SCRAPE`` (default on).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from hibs_predictor.data_quality import _has_stats, _position_ok
from hibs_predictor.fixture_utils import fixture_team_name


def thin_data_scrape_enabled() -> bool:
    if os.getenv("HIBS_SCRAPE_XG", "1").lower() in ("0", "false", "no", "off"):
        return False
    return os.getenv("HIBS_THIN_DATA_SCRAPE", "1").lower() not in ("0", "false", "no", "off")


def fotmob_recent_enabled() -> bool:
    if not thin_data_scrape_enabled():
        return False
    return os.getenv("HIBS_FOTMOB_RECENT", "1").lower() not in ("0", "false", "no", "off")


def enriched_needs_thin_rescue(
    enriched: Dict[str, Any],
    home_id: Optional[int],
    away_id: Optional[int],
) -> bool:
    from hibs_predictor.data_aggregator import DataAggregator

    if DataAggregator._enriched_needs_recent_refetch(enriched, home_id, away_id):
        return True
    try:
        nh = int(float(enriched.get("home_recent_n") or 0))
        na = int(float(enriched.get("away_recent_n") or 0))
    except (TypeError, ValueError):
        nh, na = 0, 0
    if nh < 3 or na < 3:
        return True
    if home_id and DataAggregator._team_stats_sparse(enriched.get("home_stats")):
        return True
    if away_id and DataAggregator._team_stats_sparse(enriched.get("away_stats")):
        return True
    hp = enriched.get("home_position") or {}
    ap = enriched.get("away_position") or {}
    if not (_position_ok(hp) and _position_ok(ap)):
        return True
    return False


def _merge_stats_sparse(current: Any, scraped: Dict[str, Any]) -> Dict[str, Any]:
    from hibs_predictor.data_aggregator import DataAggregator

    cur = dict(current) if isinstance(current, dict) else {}
    if not scraped:
        return cur
    if DataAggregator._team_stats_sparse(cur):
        return {**scraped, **{k: v for k, v in cur.items() if v not in (None, "", 0)}}
    if not _has_stats(cur) and _has_stats(scraped):
        return scraped
    return cur


def apply_supplemental_table_fields(enriched: Dict[str, Any], supplemental: Dict[str, Any]) -> bool:
    """Apply SoccerStats positions from supplemental when enrich did not set them."""
    if not supplemental:
        return False
    from hibs_predictor.scrapers import soccerstats_standings as sstats

    changed = False
    league_code = str(enriched.get("league") or "")
    if league_code not in sstats.LEAGUE_PARAM:
        return False
    home_nm = fixture_team_name(enriched, "home")
    away_nm = fixture_team_name(enriched, "away")
    if not (_position_ok(enriched.get("home_position")) and _position_ok(enriched.get("away_position"))):
        try:
            rows = sstats.fetch_league_table(league_code)
            if rows:
                if not _position_ok(enriched.get("home_position")) and home_nm:
                    sr = sstats.find_team_row(rows, home_nm)
                    if sr:
                        enriched["home_position"] = sstats.row_to_position_shape(sr)
                        changed = True
                if not _position_ok(enriched.get("away_position")) and away_nm:
                    sr_a = sstats.find_team_row(rows, away_nm)
                    if sr_a:
                        enriched["away_position"] = sstats.row_to_position_shape(sr_a)
                        changed = True
        except Exception:
            pass
    return changed


def apply_fotmob_table_stats(enriched: Dict[str, Any], league_code: str) -> bool:
    from hibs_predictor.scrapers import fotmob_client as fm

    if league_code not in fm.FOTMOB_LEAGUE_IDS:
        return False
    home_nm = fixture_team_name(enriched, "home")
    away_nm = fixture_team_name(enriched, "away")
    changed = False
    stats_fn = (
        fm.team_season_stats_from_national_fotmob
        if league_code == "INTL_FRIENDLIES"
        else fm.team_season_stats_from_fotmob_league
    )
    if not _has_stats(enriched.get("home_stats")) and home_nm:
        st = stats_fn(league_code, home_nm)
        if st:
            enriched["home_stats"] = _merge_stats_sparse(enriched.get("home_stats"), st)
            changed = True
    if not _has_stats(enriched.get("away_stats")) and away_nm:
        st_a = stats_fn(league_code, away_nm)
        if st_a:
            enriched["away_stats"] = _merge_stats_sparse(enriched.get("away_stats"), st_a)
            changed = True
    return changed


def recompute_recent_derived(
    enriched: Dict[str, Any],
    *,
    home_id: Optional[int],
    away_id: Optional[int],
    home_name: str,
    away_name: str,
) -> bool:
    """Re-run rates and form after FotMob recent fill."""
    from hibs_predictor.betting_engine import TeamStrengthCalculator
    from hibs_predictor.data_aggregator import _recent_match_rates

    if not enriched.get("home_recent") and not enriched.get("away_recent"):
        return False
    home_rates = _recent_match_rates(
        enriched.get("home_recent") or [], home_id or 0, team_name=home_name
    )
    away_rates = _recent_match_rates(
        enriched.get("away_recent") or [], away_id or 0, team_name=away_name
    )
    enriched["home_btts_rate"] = home_rates["btts_rate"]
    enriched["away_btts_rate"] = away_rates["btts_rate"]
    enriched["home_recent_n"] = int(home_rates["n"])
    enriched["away_recent_n"] = int(away_rates["n"])
    enriched["home_over25_rate"] = home_rates["over25_rate"]
    enriched["away_over25_rate"] = away_rates["over25_rate"]
    enriched["home_over15_rate"] = home_rates["over15_rate"]
    enriched["away_over15_rate"] = away_rates["over15_rate"]
    enriched["home_form"] = TeamStrengthCalculator.calculate_form_strength(
        enriched.get("home_recent") or [], home_id, team_name=home_name
    )
    enriched["away_form"] = TeamStrengthCalculator.calculate_form_strength(
        enriched.get("away_recent") or [], away_id, team_name=away_name
    )
    enriched["home_home_factor"] = TeamStrengthCalculator.calculate_home_away_factor(
        home_id, enriched.get("home_recent") or [], is_home=True, team_name=home_name
    )
    enriched["away_away_factor"] = TeamStrengthCalculator.calculate_home_away_factor(
        away_id, enriched.get("away_recent") or [], is_home=False, team_name=away_name
    )
    return True


def apply_thin_data_rescue(
    enriched: Dict[str, Any],
    fixture: Dict[str, Any],
    league_code: str,
    *,
    home_id: Optional[int],
    away_id: Optional[int],
    supplemental: Optional[Dict[str, Any]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Fill thin blocks from FotMob calendar + league tables and supplemental standings."""
    if not thin_data_scrape_enabled():
        return enriched
    from hibs_predictor.tournament_focus import friendlies_max_data_active

    if not force and not friendlies_max_data_active(league_code=league_code):
        if not enriched_needs_thin_rescue(enriched, home_id, away_id):
            return enriched

    meta = enriched.setdefault("thin_data_rescue", {})
    home_nm = fixture_team_name(fixture, "home") or fixture_team_name(enriched, "home")
    away_nm = fixture_team_name(fixture, "away") or fixture_team_name(enriched, "away")
    changed_parts: list[str] = []

    if fotmob_recent_enabled():
        from hibs_predictor.scrapers import fotmob_client as fm

        if home_nm and not (enriched.get("home_recent") or []):
            recent_h = fm.team_recent_from_fotmob_calendar(league_code, home_nm)
            if recent_h:
                enriched["home_recent"] = recent_h
                meta["home_recent_source"] = "fotmob_calendar"
                changed_parts.append("home_recent")
        if away_nm and not (enriched.get("away_recent") or []):
            recent_a = fm.team_recent_from_fotmob_calendar(league_code, away_nm)
            if recent_a:
                enriched["away_recent"] = recent_a
                meta["away_recent_source"] = "fotmob_calendar"
                changed_parts.append("away_recent")

    if apply_fotmob_table_stats(enriched, league_code):
        changed_parts.append("fotmob_table_stats")

    if supplemental and apply_supplemental_table_fields(enriched, supplemental):
        changed_parts.append("soccerstats_positions")

    if league_code == "EPL":
        from hibs_predictor.scrapers import fpl_client as fpl

        if fpl.fpl_epl_enabled():
            if home_nm and not (enriched.get("home_recent") or []):
                recent_h = fpl.team_recent_from_fpl(home_nm)
                if recent_h:
                    enriched["home_recent"] = recent_h
                    meta["home_recent_source"] = "fpl_fixtures"
                    changed_parts.append("home_recent_fpl")
            if away_nm and not (enriched.get("away_recent") or []):
                recent_a = fpl.team_recent_from_fpl(away_nm)
                if recent_a:
                    enriched["away_recent"] = recent_a
                    meta["away_recent_source"] = "fpl_fixtures"
                    changed_parts.append("away_recent_fpl")
            from hibs_predictor.data_quality import _position_ok

            if home_nm and not _position_ok(enriched.get("home_position")):
                row_h = fpl.team_position_row(home_nm)
                if row_h:
                    enriched["home_position"] = {
                        "rank": row_h.get("rank"),
                        "points": row_h.get("points"),
                        "played": row_h.get("played"),
                        "source": "fpl_api",
                    }
                    changed_parts.append("home_position_fpl")
            if away_nm and not _position_ok(enriched.get("away_position")):
                row_a = fpl.team_position_row(away_nm)
                if row_a:
                    enriched["away_position"] = {
                        "rank": row_a.get("rank"),
                        "points": row_a.get("points"),
                        "played": row_a.get("played"),
                        "source": "fpl_api",
                    }
                    changed_parts.append("away_position_fpl")

    if changed_parts:
        recompute_recent_derived(
            enriched,
            home_id=home_id,
            away_id=away_id,
            home_name=home_nm or "",
            away_name=away_nm or "",
        )
        meta["applied"] = changed_parts
    return enriched
