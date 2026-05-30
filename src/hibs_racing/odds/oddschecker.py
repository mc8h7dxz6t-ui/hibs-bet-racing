from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd

from hibs_racing.config import load_config
from hibs_racing.odds.fractions import fraction_to_decimal
from hibs_racing.odds.matching import horse_names_match, normalize_horse_name

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

EXCHANGE_BOOKS = {
    "betfair exchange",
    "betfair",
    "betdaq",
    "matchbook",
    "smarkets",
}


@dataclass
class OddscheckerFetchReport:
    races_attempted: int
    races_matched: int
    runners_priced: int
    errors: list[str]

    def to_dict(self) -> dict:
        return {
            "races_attempted": self.races_attempted,
            "races_matched": self.races_matched,
            "runners_priced": self.runners_priced,
            "errors": self.errors,
        }


def _get_session():
    try:
        import requests
    except ImportError as exc:
        raise ImportError('Install scraper extra: pip install -e ".[scraper]"') from exc
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def _parse_html_table(html: str) -> pd.DataFrame | None:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise ImportError('Install scraper extra: pip install -e ".[scraper]"') from exc

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_=re.compile(r"eventTable", re.I))
    if table is None:
        table = soup.find("table", {"class": "eventTable "})
    if table is None:
        return None

    frames = pd.read_html(StringIO(str(table)))
    if not frames:
        return None
    df = frames[0].dropna(how="all")
    if df.empty:
        return None
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def _book_columns(df: pd.DataFrame, *, retail_only: bool = True) -> list[str]:
    cols: list[str] = []
    for col in df.columns:
        key = str(col).strip().lower()
        if key in {"winner", "selection", "name", "horse", "unnamed: 0"}:
            continue
        if retail_only and key in EXCHANGE_BOOKS:
            continue
        if "exchange" in key or key.endswith(" exchange"):
            continue
        cols.append(col)
    return cols


def _row_best_price(row: pd.Series, book_cols: list[str]) -> tuple[float | None, str | None]:
    best: float | None = None
    best_book: str | None = None
    for col in book_cols:
        price = fraction_to_decimal(row.get(col))
        if price is None:
            continue
        if best is None or price > best:
            best = price
            best_book = col
    return best, best_book


def search_race_url(query: str, *, session=None, base_url: str = "https://www.oddschecker.com") -> str | None:
    session = session or _get_session()
    url = f"{base_url.rstrip('/')}/search/process?from=1&limit=10&query={quote_plus(query)}"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    results = payload.get("search_results", {}).get("search_results") or []
    if not results:
        return None
    path = results[0].get("market_map") or results[0].get("url")
    if not path:
        return None
    if str(path).startswith("http"):
        return str(path)
    return f"{base_url.rstrip('/')}/{str(path).lstrip('/')}"


def fetch_race_odds_page(
    url: str,
    *,
    session=None,
    retail_only: bool = True,
) -> pd.DataFrame:
    """Parse an Oddschecker race winner market into horse × bookmaker prices."""
    session = session or _get_session()
    resp = session.get(url, timeout=45)
    resp.raise_for_status()
    table = _parse_html_table(resp.text)
    if table is None:
        raise ValueError(f"No odds table found at {url}")

    name_col = None
    for candidate in ("winner", "selection", "name", "horse"):
        if candidate in table.columns:
            name_col = candidate
            break
    if name_col is None:
        name_col = table.columns[0]

    books = _book_columns(table, retail_only=retail_only)
    rows: list[dict] = []
    for _, row in table.iterrows():
        horse = str(row.get(name_col) or "").strip()
        if not horse or horse.lower() in {"nr", "non runner"}:
            continue
        best, book = _row_best_price(row, books)
        if best is None:
            continue
        rows.append(
            {
                "horse_name": horse,
                "win_decimal": best,
                "best_book": book,
                "odds_source": "oddschecker",
                "odds_url": url,
            }
        )
    return pd.DataFrame(rows)


def _race_search_query(course: str | None, off_time: str | None, race_name: str | None) -> str:
    parts = [p for p in (course, off_time, race_name) if p]
    return " ".join(parts)


def fetch_oddschecker_odds(
    cards: pd.DataFrame,
    *,
    config_path: Path | None = None,
    race_urls: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, OddscheckerFetchReport]:
    """
    Scrape retail bookmaker win prices from Oddschecker for card races.
    Returns odds frame (horse_name, win_decimal, best_book, …) aligned for score-card merge.
    """
    cfg = load_config(config_path).get("oddschecker", {})
    if not cfg.get("enabled", True):
        return pd.DataFrame(), OddscheckerFetchReport(0, 0, 0, ["oddschecker disabled in config"])

    session = _get_session()
    base_url = cfg.get("base_url", "https://www.oddschecker.com")
    pause = float(cfg.get("request_pause_sec", 1.5))
    place_fraction = float(cfg.get("default_place_fraction", 0.25))
    places = int(cfg.get("default_places", 3))
    retail_only = bool(cfg.get("retail_only", True))
    race_urls = race_urls or {}

    errors: list[str] = []
    priced: list[dict] = []
    races = list(cards.groupby("race_id", sort=False))
    matched = 0

    for race_id, race_df in races:
        first = race_df.iloc[0]
        url = race_urls.get(str(race_id)) or race_urls.get(str(first.get("race_natural_key") or ""))
        if not url:
            query = _race_search_query(first.get("course"), first.get("off_time"), first.get("race_name"))
            try:
                url = search_race_url(query, session=session, base_url=base_url)
            except Exception as exc:
                errors.append(f"{race_id}: search failed — {exc}")
                time.sleep(pause)
                continue
        if not url:
            errors.append(f"{race_id}: no Oddschecker URL for '{query}'")
            time.sleep(pause)
            continue

        try:
            oc = fetch_race_odds_page(url, session=session, retail_only=retail_only)
            matched += 1
        except Exception as exc:
            errors.append(f"{race_id}: scrape failed — {exc}")
            time.sleep(pause)
            continue

        for _, card_row in race_df.iterrows():
            horse = card_row.get("horse_name")
            hit = None
            for _, oc_row in oc.iterrows():
                if horse_names_match(horse, oc_row.get("horse_name")):
                    hit = oc_row
                    break
            if hit is None:
                continue
            priced.append(
                {
                    "race_id": race_id,
                    "runner_id": card_row.get("runner_id"),
                    "horse_name": horse,
                    "win_decimal": float(hit["win_decimal"]),
                    "best_book": hit.get("best_book"),
                    "place_fraction": place_fraction,
                    "places": places,
                    "odds_source": "oddschecker",
                    "odds_url": url,
                }
            )
        time.sleep(pause)

    odds = pd.DataFrame(priced)
    report = OddscheckerFetchReport(
        races_attempted=len(races),
        races_matched=matched,
        runners_priced=len(odds),
        errors=errors,
    )
    return odds, report


def merge_odds_to_cards(cards: pd.DataFrame, odds: pd.DataFrame) -> pd.DataFrame:
    """Attach best retail prices onto card rows (updates win_decimal)."""
    if odds.empty:
        return cards
    out = cards.copy()
    if "win_decimal" not in out.columns:
        out["win_decimal"] = None
    if "best_book" not in out.columns:
        out["best_book"] = None

    for idx, row in out.iterrows():
        match = None
        if "runner_id" in odds.columns and pd.notna(row.get("runner_id")):
            hits = odds[odds["runner_id"] == row["runner_id"]]
            if not hits.empty:
                match = hits.iloc[0]
        if match is None and pd.notna(row.get("horse_name")):
            for _, oc in odds.iterrows():
                if horse_names_match(row.get("horse_name"), oc.get("horse_name")):
                    match = oc
                    break
        if match is not None:
            out.at[idx, "win_decimal"] = match.get("win_decimal")
            out.at[idx, "best_book"] = match.get("best_book")
            out.at[idx, "odds_source"] = match.get("odds_source", "oddschecker")
    return out


def load_race_urls_file(path: Path) -> dict[str, str]:
    """JSON map race_id → oddschecker URL for brittle days."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return {str(k): str(v) for k, v in payload.items()}
    raise ValueError("race URLs file must be a JSON object {race_id: url}")
