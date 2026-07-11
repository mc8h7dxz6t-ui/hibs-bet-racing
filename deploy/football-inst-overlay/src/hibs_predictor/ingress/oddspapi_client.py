"""OddsPapi (oddspapi.io) client — sharp unfiltered Pinnacle / Singbet / Betfair Exchange."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from hibs_predictor.api_clients import BaseApiClient
from hibs_predictor.ingress.price_truth_ingress import oddspapi_event_to_bookmaker_panel
from hibs_predictor.ingress.schema_guard import IngressRejectError, validate_ingress_payload


class OddsPapiClient(BaseApiClient):
    """
    Direct sharp feed ingress. Replaces retail Odds API aggregation path when enabled.

    Env:
      ODDSPAPI_API_KEY
      ODDSPAPI_BASE_URL (default https://api.oddspapi.io/v1)
      ODDSPAPI_SCHEMA_MIN (default 1.0.0)
    """

    SPORT_SLUGS = {
        "EPL": "soccer-england-premier-league",
        "CHAMPIONSHIP": "soccer-england-championship",
        "LA_LIGA": "soccer-spain-la-liga",
        "SERIE_A": "soccer-italy-serie-a",
        "BUNDESLIGA": "soccer-germany-bundesliga",
        "LIGUE_1": "soccer-france-ligue-1",
        "UCL": "soccer-uefa-champions-league",
        "SCOTLAND": "soccer-scotland-premiership",
        "NORWAY_ELITESERIEN": "soccer-norway-eliteserien",
        "FINLAND_VEIKKAUSLIIGA": "soccer-finland-veikkausliiga",
    }

    SHARP_BOOKS = ("pinnacle", "singbet", "betfair")

    def __init__(self, api_key: str, *, base_url: Optional[str] = None) -> None:
        root = (base_url or os.getenv("ODDSPAPI_BASE_URL") or "https://api.oddspapi.io/v1").rstrip("/")
        super().__init__(api_key, root, "Authorization", "oddspapi")
        self._schema_min = os.getenv("ODDSPAPI_SCHEMA_MIN", "1.0.0")

    def _get_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

    def fetch_odds_for_league(self, league_code: str) -> List[Dict[str, Any]]:
        slug = self.SPORT_SLUGS.get(league_code)
        if not slug:
            return []
        cache_key = f"oddspapi_league_{league_code}"
        cached = self.cache.get(cache_key, ttl_hours=1)
        if cached is not None:
            return cached
        params = {
            "sport": slug,
            "books": ",".join(self.SHARP_BOOKS),
            "markets": "h2h",
            "oddsFormat": "decimal",
        }
        import requests

        url = f"{self.base_url}/odds"
        resp = requests.get(url, headers=self._get_headers(), params=params, timeout=25)
        if resp.status_code == 429:
            self.rate_limiter.trip_service("oddspapi")
            return []
        resp.raise_for_status()
        body = resp.json()
        events = body.get("events") if isinstance(body, dict) else body
        if not isinstance(events, list):
            raise IngressRejectError("oddspapi response missing events list")
        out: List[Dict[str, Any]] = []
        for raw in events:
            if not isinstance(raw, dict):
                continue
            wrapped = dict(raw)
            if "schema_version" not in wrapped:
                wrapped["schema_version"] = str(body.get("schema_version") or self._schema_min)
            try:
                validate_ingress_payload(
                    wrapped,
                    expected_min=self._schema_min,
                    expected_max="1.99.99",
                    required_paths=("event_id",),
                )
                panel = oddspapi_event_to_bookmaker_panel(wrapped)
            except IngressRejectError:
                continue
            out.append(
                {
                    "id": wrapped.get("event_id"),
                    "home_team": wrapped.get("home_team") or wrapped.get("home"),
                    "away_team": wrapped.get("away_team") or wrapped.get("away"),
                    "commence_time": wrapped.get("commence_time") or wrapped.get("kickoff"),
                    "bookmakers": [
                        {
                            "key": row["bookmaker"].lower().replace(" ", "_"),
                            "title": row["bookmaker"],
                            "markets": [
                                {
                                    "key": "h2h",
                                    "outcomes": [
                                        {"name": "Home", "price": row["home"]},
                                        {"name": "Draw", "price": row["draw"]},
                                        {"name": "Away", "price": row["away"]},
                                    ],
                                }
                            ],
                        }
                        for row in panel
                    ],
                    "_oddspapi_panel": panel,
                    "_ingress": "oddspapi",
                }
            )
        self.cache.set(cache_key, out, ttl_hours=1)
        return out


def oddspapi_enabled() -> bool:
    if (os.getenv("HIBS_DEPRECATE_ODDS_API") or "").strip().lower() in ("1", "true", "yes", "on"):
        return bool((os.getenv("ODDSPAPI_API_KEY") or "").strip())
    ingress = (os.getenv("HIBS_ODDS_INGRESS") or "").strip().lower()
    return ingress in ("oddspapi", "sharp", "oddspapi_sharp")
