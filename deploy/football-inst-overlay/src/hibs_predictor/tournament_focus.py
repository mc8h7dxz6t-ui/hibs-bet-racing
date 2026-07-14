"""Tournament / international focus mode (World Cup window, date-driven).

Default summer (**2026-05-20 → resume date**, before **26/27** domestic seasons): **World Cup**
is the main target (**2026-06-11 → 2026-07-18** tournament focus on the dashboard),
plus **international friendlies** and **Nordics** in the summer *intent* list (wider friendlies horizon).
**Production fetch** applies ``pipeline_excluded`` from ``config/league_profiles.yaml`` — friendlies,
Nordics, and several cups are **audit-only** (not dashboard fetch) during the elite trial.
**WORLD_CUP** and UEFA finals remain fetchable. No SPL/EPL/European league calendars until offseason ends.

``HIBS_TOURNAMENT_FOCUS=worldcup`` (or ``euros`` / ``international``) forces focus
on anytime. ``HIBS_TOURNAMENT_FOCUS=0`` forces domestic even inside the window.

When active, fixture fetch defaults to international competition codes only (fewer
API calls on VPS) and the dashboard defaults to the International region filter.
Pass ``include_domestic=True`` (dashboard ``?domestic=1``) to fetch all leagues when
the user picks All / UK / European region chips.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from hibs_predictor.config import (
    ALL_LEAGUE_CODES,
    DASHBOARD_LEAGUE_ORDER,
    _DASHBOARD_REGION_EUROPEAN,
    _DASHBOARD_REGION_UK,
)

# Core international tournament (always in active summer / WC fetch lists).
INTERNATIONAL_FOCUS_LEAGUE_CODES = [
    "WORLD_CUP",
]

INTL_FRIENDLIES_CODE = "INTL_FRIENDLIES"

# Knockout / final-stage cups only (no EPL, La Liga, etc.).
# In-season through UK/European summer — use dashboard fetch window only (typically 5 days).
_SUMMER_DAILY_LEAGUE_CODES: tuple[str, ...] = (
    "NORWAY_ELITESERIEN",
    "FINLAND_VEIKKAUSLIIGA",
    "DENMARK_SL",
)

_CUP_FINAL_LEAGUE_CODES: tuple[str, ...] = (
    "UCL",
    "EUROPA_LEAGUE",
    "UECL",
    "FA_CUP",
    "SCOTTISH_CUP",
    "LEAGUE_CUP",
    "COPA_DEL_REY",
    "COPPA_ITALIA",
    "DFB_POKAL",
    "COUPE_DE_FRANCE",
)

_DEFAULT_AUTO_START = date(2026, 6, 11)
_DEFAULT_AUTO_END = date(2026, 7, 18)
# International friendlies window (pre-World Cup block through tournament end).
_DEFAULT_FRIENDLIES_AUTO_START = date(2026, 5, 20)
# UK + most European domestic leagues are between seasons until ~August (Nordics keep playing).
_DEFAULT_DOMESTIC_OFFSEASON_START = date(2026, 5, 20)
_DEFAULT_DOMESTIC_RESUME_DATE = date(2026, 8, 1)

# Opt-in only (``HIBS_POST_WC_DOMESTIC_EUROPEAN=1``): fetch UK + European league calendars
# after the World Cup window instead of staying on Nordics / friendlies / cups until resume.
_POST_WC_DOMESTIC_EUROPEAN_CODES: tuple[str, ...] = tuple(
    sorted(
        set(_DASHBOARD_REGION_UK)
        | set(_DASHBOARD_REGION_EUROPEAN)
        | set(_SUMMER_DAILY_LEAGUE_CODES)
        | set(_CUP_FINAL_LEAGUE_CODES)
    )
)

def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _parse_date(raw: str) -> Optional[date]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _auto_window() -> tuple[date, date]:
    start = _parse_date(os.getenv("HIBS_TOURNAMENT_FOCUS_START", "")) or _DEFAULT_AUTO_START
    end = _parse_date(os.getenv("HIBS_TOURNAMENT_FOCUS_END", "")) or _DEFAULT_AUTO_END
    if end < start:
        start, end = end, start
    return start, end


def _friendlies_window() -> tuple[date, date]:
    """Calendar range when INTL_FRIENDLIES are included (through summer break / 26/27 prep)."""
    start = (
        _parse_date(os.getenv("HIBS_FRIENDLIES_FOCUS_START", ""))
        or _DEFAULT_FRIENDLIES_AUTO_START
    )
    end = _parse_date(os.getenv("HIBS_FRIENDLIES_FOCUS_END", ""))
    if end is None:
        _, off_end = _domestic_offseason_window()
        end = off_end
    if end < start:
        start, end = end, start
    return start, end


def _domestic_offseason_window() -> tuple[date, date]:
    """UK / European domestic (non-Nordic) typically idle until early August."""
    start = (
        _parse_date(os.getenv("HIBS_DOMESTIC_OFFSEASON_START", ""))
        or _DEFAULT_DOMESTIC_OFFSEASON_START
    )
    end = (
        _parse_date(os.getenv("HIBS_DOMESTIC_RESUME_DATE", ""))
        or _parse_date(os.getenv("HIBS_DOMESTIC_OFFSEASON_END", ""))
        or _DEFAULT_DOMESTIC_RESUME_DATE
    )
    if end < start:
        start, end = end, start
    return start, end


def domestic_offseason_active(*, today: Optional[date] = None) -> bool:
    """
    True when UK + European domestic leagues should be skipped from default fetch.

    Override: ``HIBS_FETCH_ALL_DOMESTIC=1`` always fetches everything;
    ``HIBS_DOMESTIC_OFFSEASON=0`` disables the summer trim even in the window.
    """
    if _env_truthy("HIBS_FETCH_ALL_DOMESTIC"):
        return False
    if _focus_explicitly_disabled():
        return False
    raw = (os.getenv("HIBS_DOMESTIC_OFFSEASON") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    cur = today if today is not None else _today_utc()
    start, end = _domestic_offseason_window()
    return start <= cur < end


def summer_daily_league_codes() -> tuple[str, ...]:
    """Nordics: peer daily options on the 5-day dashboard window (not friendlies horizon)."""
    return _SUMMER_DAILY_LEAGUE_CODES


def is_summer_daily_league(league_code: str) -> bool:
    """True for Nordic codes (summer peer daily leagues)."""
    return (league_code or "").strip().upper() in _SUMMER_DAILY_LEAGUE_CODES


def post_wc_domestic_european_active(*, today: Optional[date] = None) -> bool:
    """
    Opt-in post-WC UK + European domestic fetch (Jul–Aug gap before seasons resume).

    Default **off** — summer fetch stays Nordics / friendlies / cups until
    ``HIBS_DOMESTIC_RESUME_DATE`` (or ``HIBS_DOMESTIC_OFFSEASON_END``). Set
    ``HIBS_POST_WC_DOMESTIC_EUROPEAN=1`` to restore the old post-WC UK/EU trim.
    """
    raw = (os.getenv("HIBS_POST_WC_DOMESTIC_EUROPEAN") or "").strip().lower()
    if raw not in ("1", "true", "yes", "on"):
        return False
    if tournament_focus_active(today=today):
        return False
    if not domestic_offseason_active(today=today):
        return False
    cur = today if today is not None else _today_utc()
    _, wc_end = _auto_window()
    _, off_end = _domestic_offseason_window()
    return wc_end < cur < off_end


def post_wc_domestic_european_league_codes() -> List[str]:
    """UK + European domestic leagues for the post-WC summer gap."""
    seen: set[str] = set()
    out: List[str] = []
    for code in _POST_WC_DOMESTIC_EUROPEAN_CODES:
        c = (code or "").strip().upper()
        if c and c in ALL_LEAGUE_CODES and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def active_competition_league_codes(*, today: Optional[date] = None) -> List[str]:
    """
    Summer / focus fetch list: World Cup first, then friendlies, Nordics (5-day), cups.
    Post-WC gap (Jul–Aug): same summer list unless ``HIBS_POST_WC_DOMESTIC_EUROPEAN=1``.
    """
    if post_wc_domestic_european_active(today=today):
        return post_wc_domestic_european_league_codes()

    seen: set[str] = set()
    out: List[str] = []

    def _add(code: str) -> None:
        c = (code or "").strip().upper()
        if c and c in ALL_LEAGUE_CODES and c not in seen:
            seen.add(c)
            out.append(c)

    for code in INTERNATIONAL_FOCUS_LEAGUE_CODES:
        _add(code)
    if _friendlies_in_focus(today=today):
        _add(INTL_FRIENDLIES_CODE)
    if domestic_offseason_active(today=today):
        for code in _SUMMER_DAILY_LEAGUE_CODES:
            _add(code)
    # During active WC/Euros focus, UEFA/domestic cup calendars are offseason — skip FDO 403 spam.
    include_cups = not tournament_focus_active(today=today) or _env_truthy("HIBS_WC_INCLUDE_CUP_FINALS")
    if include_cups:
        for code in _CUP_FINAL_LEAGUE_CODES:
            _add(code)
    extra = (os.getenv("HIBS_ACTIVE_EXTRA_LEAGUES") or "").strip()
    if extra:
        for raw in extra.split(","):
            _add(raw.strip().upper())
    return out


def summer_active_league_codes(*, today: Optional[date] = None) -> List[str]:
    """Alias for active summer / WC fetch list."""
    return active_competition_league_codes(today=today)


def friendlies_window_active(*, today: Optional[date] = None) -> bool:
    cur = today if today is not None else _today_utc()
    start, end = _friendlies_window()
    return start <= cur <= end


def before_world_cup_start(*, today: Optional[date] = None) -> bool:
    """True on calendar dates strictly before the World Cup auto-focus window opens."""
    cur = today if today is not None else _today_utc()
    wc_start, _ = _auto_window()
    return cur < wc_start


def friendlies_max_data_profile_enabled(*, today: Optional[date] = None) -> bool:
    """
    Optional window-wide max-data for ``INTL_FRIENDLIES`` (heavy scrapers, 14-day horizon).

    Off by default — friendlies have high squad rotation; standard enrich still targets
    85%+ DQ. Enable only with ``HIBS_FRIENDLIES_MAX_DATA=1`` (not implied by ``HIBS_MAX_DATA``).
    """
    if not _env_truthy("HIBS_FRIENDLIES_MAX_DATA"):
        return False
    if not friendlies_window_active(today=today):
        return False
    return before_world_cup_start(today=today)


def friendlies_max_data_active(
    *,
    league_code: Optional[str] = None,
    today: Optional[date] = None,
) -> bool:
    """Max-data deep enrich / supplemental scrapers for ``INTL_FRIENDLIES`` before WC."""
    if not friendlies_max_data_profile_enabled(today=today):
        return False
    if league_code is None:
        return True
    return (league_code or "").strip().upper() == INTL_FRIENDLIES_CODE


def friendlies_fetch_window_days(*, dashboard_days: int = 5) -> int:
    """Fixture horizon for INTL_FRIENDLIES during the pre–World Cup friendlies block."""
    if not friendlies_window_active():
        return max(1, int(dashboard_days))
    try:
        want = int(os.getenv("HIBS_FRIENDLIES_FETCH_DAYS", "14"))
    except ValueError:
        want = 14
    want = max(7, min(21, want))
    return max(max(1, int(dashboard_days)), want)


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _focus_explicitly_disabled() -> bool:
    raw = (os.getenv("HIBS_TOURNAMENT_FOCUS") or "").strip().lower()
    return raw in ("0", "false", "no", "off", "none", "disabled")


def _mode_from_env_raw(raw: str) -> Optional[str]:
    if raw in ("worldcup", "world_cup", "wc", "fifa"):
        return "worldcup"
    if raw in ("euros", "euro", "ec"):
        return "euros"
    if raw in ("international", "intl", "nations"):
        return "international"
    if raw in ("1", "true", "yes", "on"):
        return "worldcup"
    return None


def _friendlies_in_focus(*, today: Optional[date] = None) -> bool:
    """Include international friendlies in international focus fetch lists."""
    if _env_truthy("HIBS_TOURNAMENT_INCLUDE_FRIENDLIES"):
        return True
    if friendlies_window_active(today=today):
        return True
    return tournament_focus_mode(today=today) == "worldcup"


def international_focus_league_codes(*, today: Optional[date] = None) -> List[str]:
    """League codes fetched when tournament focus is on and domestic is excluded."""
    return active_competition_league_codes(today=today)


def tournament_focus_mode(*, today: Optional[date] = None) -> Optional[str]:
    """Active focus slug (worldcup / euros / international) or None when off."""
    if _focus_explicitly_disabled():
        return None

    raw = (os.getenv("HIBS_TOURNAMENT_FOCUS") or "").strip().lower()
    mode = _mode_from_env_raw(raw)
    if mode:
        return mode
    if _env_truthy("HIBS_FOCUS_INTERNATIONAL"):
        return "international"

    if raw:
        return None

    cur = today if today is not None else _today_utc()
    start, end = _auto_window()
    if start <= cur <= end:
        return "worldcup"
    return None


def tournament_focus_active(*, today: Optional[date] = None) -> bool:
    return tournament_focus_mode(today=today) is not None


def tournament_focus_label(*, today: Optional[date] = None) -> str:
    mode = tournament_focus_mode(today=today)
    if mode == "worldcup":
        return "World Cup focus"
    if mode == "euros":
        return "Euros focus"
    if mode == "international":
        return "International focus"
    return ""


def dashboard_default_region(*, today: Optional[date] = None) -> str:
    """
    Default region chip on the dashboard.

    World Cup window: International (friendlies + WC in that chip).
    Post-WC summer gap (opt-in UK/EU fetch): All region when ``HIBS_POST_WC_DOMESTIC_EUROPEAN=1``.
    Pre-WC summer / domestic offseason: All — UEFA finals (UCL/EL/UECL) are fetched but
    use the European region slug, so International-only hides Conference League tonight.
    """
    if tournament_focus_active(today=today):
        return "international"
    if post_wc_domestic_european_active(today=today):
        return ""
    if domestic_offseason_active(today=today):
        return ""
    if friendlies_window_active(today=today):
        return ""
    return ""


def league_codes_for_fetch(
    *,
    today: Optional[date] = None,
    include_domestic: bool = False,
) -> List[str]:
    from hibs_predictor.league_profiles import apply_production_pipeline_filter

    if include_domestic:
        codes = list(ALL_LEAGUE_CODES)
    elif tournament_focus_active(today=today) or domestic_offseason_active(today=today):
        codes = active_competition_league_codes(today=today)
    else:
        codes = list(ALL_LEAGUE_CODES)
    return apply_production_pipeline_filter(codes)


def effective_dashboard_league_order(
    *,
    today: Optional[date] = None,
    include_domestic: bool = False,
) -> List[str]:
    from hibs_predictor.league_profiles import apply_production_pipeline_filter

    if include_domestic:
        codes = list(DASHBOARD_LEAGUE_ORDER)
    elif tournament_focus_active(today=today) or domestic_offseason_active(today=today):
        codes = active_competition_league_codes(today=today)
    else:
        codes = list(DASHBOARD_LEAGUE_ORDER)
    return apply_production_pipeline_filter(codes)


def prioritize_fixtures_for_focus(
    fixtures: List[Dict[str, Any]],
    *,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """International fixtures first for assistant / summaries when focus or friendlies window is on."""
    if (
        not tournament_focus_active(today=today)
        and not friendlies_window_active(today=today)
        and not domestic_offseason_active(today=today)
    ):
        return list(fixtures or [])
    intl = set(active_competition_league_codes(today=today))
    primary: List[Dict[str, Any]] = []
    secondary: List[Dict[str, Any]] = []
    for row in fixtures or []:
        if str(row.get("league") or "") in intl:
            primary.append(row)
        else:
            secondary.append(row)
    order = {code: i for i, code in enumerate(active_competition_league_codes(today=today))}
    primary.sort(
        key=lambda f: (
            order.get(str(f.get("league") or ""), 99),
            f.get("kickoff_sort") or f.get("date") or "",
        )
    )
    secondary.sort(key=lambda f: f.get("kickoff_sort") or f.get("date") or "")
    return primary + secondary


def tournament_focus_context(
    *,
    today: Optional[date] = None,
    include_domestic: bool = False,
) -> Dict[str, Any]:
    active = tournament_focus_active(today=today)
    mode = tournament_focus_mode(today=today) or ""
    start, end = _auto_window()
    fr_start, fr_end = _friendlies_window()
    off_season = domestic_offseason_active(today=today)
    off_start, off_end = _domestic_offseason_window()
    intl_only = (active or off_season) and not include_domestic
    post_wc = post_wc_domestic_european_active(today=today)
    return {
        "active": active,
        "mode": mode,
        "label": tournament_focus_label(today=today) if active else "",
        "post_wc_domestic_european_active": post_wc,
        "post_wc_label": "UK + European leagues" if post_wc else "",
        "default_region": dashboard_default_region(today=today),
        "fetch_leagues": list(league_codes_for_fetch(today=today, include_domestic=include_domestic)),
        "include_friendlies": _friendlies_in_focus(today=today),
        "friendlies_window_active": friendlies_window_active(today=today),
        "friendlies_max_data_active": friendlies_max_data_profile_enabled(today=today),
        "domestic_offseason_active": off_season,
        "domestic_offseason_start": off_start.isoformat(),
        "domestic_offseason_end": off_end.isoformat(),
        "active_competition_leagues": active_competition_league_codes(today=today),
        "summer_daily_leagues": list(_SUMMER_DAILY_LEAGUE_CODES),
        "cup_final_leagues": list(_CUP_FINAL_LEAGUE_CODES),
        "intl_only_fetch": intl_only,
        "auto_window_start": start.isoformat(),
        "auto_window_end": end.isoformat(),
        "friendlies_window_start": fr_start.isoformat(),
        "friendlies_window_end": fr_end.isoformat(),
    }
