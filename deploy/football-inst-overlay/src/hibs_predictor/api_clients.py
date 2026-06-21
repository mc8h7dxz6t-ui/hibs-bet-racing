import os
import time
from typing import Any, Dict, List, Optional

import requests

from hibs_predictor.app_logging import get_logger, log_resilience_event
from hibs_predictor.cache import Cache
from hibs_predictor.rate_limiter import RateLimiter

_api_log = get_logger("api_clients")


_API_SPORTS_MISSING_KEY_WARNED = False


def _retry_after_seconds(response: requests.Response, attempt: int) -> float:
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return min(60.0, max(1.0, float(raw)))
        except (TypeError, ValueError):
            pass
    return min(30.0, 2.0 ** attempt)


def _http_get_with_backoff(
    url: str,
    *,
    headers: Dict[str, str],
    params: Optional[Dict[str, Any]],
    timeout: float,
    service_label: str,
    max_retries: int = 3,
    max_rate_limit_wait: Optional[float] = None,
) -> requests.Response:
    """HTTP GET with retries. ``max_rate_limit_wait=0`` skips long sleeps (optional enrich paths)."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params or {}, timeout=timeout)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt + 1 >= max_retries:
                raise
            time.sleep(min(30.0, 2.0 ** attempt))
            continue
        if response.status_code in (429, 503):
            wait = _retry_after_seconds(response, attempt)
            if max_rate_limit_wait is not None:
                if max_rate_limit_wait <= 0:
                    print(
                        f"[{service_label} HTTP {response.status_code}] soft-fail (no backoff) "
                        f"{url.rsplit('/', 1)[-1] if url else 'request'}"
                    )
                    return response
                wait = min(wait, float(max_rate_limit_wait))
            print(f"[{service_label} HTTP {response.status_code}] backoff {wait:.1f}s (attempt {attempt + 1}/{max_retries})")
            if attempt + 1 >= max_retries:
                response.raise_for_status()
            time.sleep(wait)
            continue
        return response
    if last_exc:
        raise last_exc
    raise requests.RequestException(f"{service_label} request failed after retries")


def _api_sports_errors_indicate_missing_or_invalid_key(errors: Any) -> bool:
    text = str(errors).lower()
    if "application key" in text:
        return True
    if "missing" in text and "key" in text:
        return True
    if "invalid" in text and "key" in text:
        return True
    return False


def _api_football_errors_truthy(errors: Any) -> bool:
    if errors is None:
        return False
    if isinstance(errors, str):
        return bool(errors.strip())
    if isinstance(errors, list):
        return len(errors) > 0
    if isinstance(errors, dict):
        return len(errors) > 0
    return bool(errors)


def _local_guard_stale_response(
    client: "BaseApiClient",
    cache_key: str,
    *,
    use_cache: bool,
) -> Optional[Dict[str, Any]]:
    reason = client.rate_limiter.block_reason(client.service_name)
    if not reason:
        return None
    if use_cache:
        stale = client.cache.peek(cache_key)
        if isinstance(stale, dict):
            log_resilience_event(
                _api_log,
                "rate_limit_stale_reuse",
                service=client.service_name,
                block_reason=reason,
                cache_key=cache_key[:80],
            )
            return stale
    log_resilience_event(
        _api_log,
        "rate_limit_guard_blocked",
        service=client.service_name,
        block_reason=reason,
    )
    return None


def _api_football_rate_limited(errors: Any) -> bool:
    if not isinstance(errors, dict):
        return False
    for key, val in errors.items():
        text = f"{key} {val}".lower()
        if "ratelimit" in text.replace("_", "") or "too many requests" in text:
            return True
        if "request limit for the day" in text or ("daily" in text and "limit" in text):
            return True
    return False


def _api_football_daily_quota_exhausted(errors: Any) -> bool:
    if not isinstance(errors, dict):
        return False
    for key, val in errors.items():
        text = f"{key} {val}".lower()
        if "request limit for the day" in text:
            return True
    return False


class BaseApiClient:
    def __init__(self, api_key: str, base_url: str, header_name: str, service_name: str) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.header_name = header_name
        self.service_name = service_name
        self.cache = Cache()
        self.rate_limiter = RateLimiter()

    def _get_headers(self) -> Dict[str, str]:
        return {self.header_name: self.api_key}

    def _cache_ttl_hours(self, endpoint: str) -> float:
        return 4.0

    def _get_json(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
        *,
        ttl_hours: Optional[float] = None,
    ) -> Dict[str, Any]:
        cache_key = f"{self.service_name}_{endpoint}_{str(params)}"
        ttl = float(ttl_hours) if ttl_hours is not None else self._cache_ttl_hours(endpoint)

        if use_cache:
            cached = self.cache.get(cache_key, ttl_hours=ttl)
            if cached:
                return cached

        guarded = _local_guard_stale_response(self, cache_key, use_cache=use_cache)
        if guarded is not None:
            if "error" in guarded and len(guarded) == 1:
                return guarded
            return guarded
        if self.rate_limiter.block_reason(self.service_name):
            return {"error": "Rate limit exceeded. Try again later."}

        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        response = _http_get_with_backoff(
            url,
            headers=self._get_headers(),
            params=params,
            timeout=20,
            service_label=self.service_name,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 429:
                self._trip_provider_rate_limit()
            if use_cache:
                stale = self.cache.peek(cache_key)
                if isinstance(stale, dict):
                    log_resilience_event(
                        _api_log,
                        "provider_http_stale_reuse",
                        service=self.service_name,
                        status=status,
                        endpoint=endpoint,
                    )
                    return stale
            raise
        try:
            data = response.json()
        except ValueError as exc:
            raise ValueError(f"Invalid JSON from {self.service_name} {endpoint}: {exc}") from exc
        self.rate_limiter.record_request(self.service_name)
        self.cache.set(cache_key, data, ttl_hours=ttl)
        return data

    def _trip_provider_rate_limit(self) -> None:
        """Fill local minute guard after provider 429 so we stop hammering."""
        limit = self.rate_limiter.minute_limits.get(self.service_name, 0)
        if limit <= 0:
            return
        entry = self.rate_limiter._ensure_entry_shape(self.service_name)
        entry["minute_count"] = int(limit)
        entry["minute_reset_at"] = (
            __import__("datetime").datetime.now()
            + __import__("datetime").timedelta(minutes=1)
        ).isoformat()
        self.rate_limiter._save_state()


def football_data_requests_allowed() -> bool:
    """Respect local 10 req/min guard, optional global skip, and 403 global trip."""
    if (os.getenv("HIBS_SKIP_FOOTBALL_DATA") or "").strip().lower() in ("1", "true", "yes", "on"):
        return False
    try:
        from hibs_predictor.football_data_guard import global_forbidden_active

        if global_forbidden_active():
            return False
    except Exception:
        pass
    return RateLimiter().block_reason("football_data_org") is None


def football_data_record_request() -> None:
    """Count one Football-Data.org HTTP call against the shared minute/hour guards."""
    RateLimiter().record_request("football_data_org")


def football_data_trip_minute_guard() -> None:
    """Fill local minute guard after provider 429 (health probe and client paths)."""
    limiter = RateLimiter()
    limit = limiter.minute_limits.get("football_data_org", 0)
    if limit <= 0:
        return
    entry = limiter._ensure_entry_shape("football_data_org")
    entry["minute_count"] = int(limit)
    entry["minute_reset_at"] = (
        __import__("datetime").datetime.now() + __import__("datetime").timedelta(minutes=1)
    ).isoformat()
    limiter._save_state()


def football_data_team_matches_enabled() -> bool:
    """Per-team /teams/{id}/matches is expensive on free tier — off by default."""
    return (os.getenv("HIBS_FOOTBALL_DATA_TEAM_MATCHES") or "").strip().lower() in ("1", "true", "yes", "on")


class FootballDataOrgClient(BaseApiClient):
    def __init__(self, api_key: str) -> None:
        super().__init__(api_key, "https://api.football-data.org/v4", "X-Auth-Token", "football_data_org")
        self._standings_memo: Dict[str, List[Dict[str, Any]]] = {}

    def _cache_ttl_hours(self, endpoint: str) -> float:
        ep = endpoint.lower()
        if "standings" in ep:
            try:
                return max(1.0, float(os.getenv("HIBS_FOOTBALL_DATA_STANDINGS_CACHE_HOURS", "24")))
            except ValueError:
                return 24.0
        if "/teams/" in ep and "matches" in ep:
            try:
                return max(1.0, float(os.getenv("HIBS_FOOTBALL_DATA_TEAM_CACHE_HOURS", "24")))
            except ValueError:
                return 24.0
        if "competitions/" in ep and "matches" in ep:
            try:
                return max(1.0, float(os.getenv("HIBS_FOOTBALL_DATA_FIXTURES_CACHE_HOURS", "6")))
            except ValueError:
                return 6.0
        try:
            return max(1.0, float(os.getenv("HIBS_FOOTBALL_DATA_CACHE_HOURS", "12")))
        except ValueError:
            return 12.0

    def _get_json(self, endpoint: str, params: Optional[Dict[str, Any]] = None, use_cache: bool = True) -> Dict[str, Any]:
        """Fail-soft on quota/forbidden; long TTL caches; honour 10 req/min guard."""
        from hibs_predictor.football_data_guard import (
            block_ttl_hours,
            competition_from_endpoint,
            football_data_traffic_allowed,
            record_forbidden,
        )

        comp = competition_from_endpoint(endpoint)
        if not football_data_traffic_allowed(comp):
            return {"errorCode": 403, "message": "football-data competition blocked", "matches": [], "standings": []}

        cache_key = f"{self.service_name}_{endpoint}_{str(params)}"
        ttl = self._cache_ttl_hours(endpoint)
        if use_cache:
            cached = self.cache.get(cache_key, ttl_hours=ttl)
            if isinstance(cached, dict) and int(cached.get("errorCode") or 0) in (403, 429):
                return cached
        try:
            return super()._get_json(endpoint, params=params, use_cache=use_cache, ttl_hours=ttl)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (403, 429):
                if status == 429:
                    self._trip_provider_rate_limit()
                if status == 403 and comp:
                    record_forbidden(comp, http_status=403, reason=str(exc)[:80])
                payload = {"errorCode": status, "message": str(exc), "matches": [], "standings": []}
                if use_cache:
                    self.cache.set(cache_key, payload, ttl_hours=block_ttl_hours() if status == 403 else 2.0)
                return payload
            raise

    def fetch_fixtures(
        self,
        competition_code: str,
        season: int,
        status: Optional[str] = "SCHEDULED",
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        endpoint = f"competitions/{competition_code}/matches"
        params: Dict[str, Any] = {"season": season}
        if status:
            params["status"] = status
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        data = self._get_json(endpoint, params=params)
        if not isinstance(data, dict):
            return []
        if data.get("errorCode") or data.get("message"):
            err_code = data.get("errorCode")
            try:
                err_int = int(err_code) if err_code is not None else 0
            except (TypeError, ValueError):
                err_int = 0
            msg = str(data.get("message") or "")
            if err_int not in (403, 429) and "403" not in msg and "forbidden" not in msg.lower():
                print(f"[Football-Data.org] {competition_code}: {data.get('message', data)}")
            return []
        return data.get("matches", []) or []

    def fetch_team(self, team_id: int) -> Dict[str, Any]:
        endpoint = f"teams/{team_id}"
        return self._get_json(endpoint)

    def fetch_team_matches(self, team_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        if not football_data_team_matches_enabled():
            return []
        endpoint = f"teams/{team_id}/matches"
        params = {"limit": limit, "status": "FINISHED"}
        data = self._get_json(endpoint, params=params)
        return data.get("matches", []) or []

    def fetch_standings(self, competition_code: str, season: int) -> List[Dict[str, Any]]:
        """Documented Football-Data.org standings endpoint for current/historical tables."""
        from hibs_predictor.football_data_guard import competition_allowed, football_data_traffic_allowed

        if not football_data_traffic_allowed(competition_code):
            return []
        memo_key = f"{competition_code}_{season}"
        if memo_key in self._standings_memo:
            return self._standings_memo[memo_key]
        endpoint = f"competitions/{competition_code}/standings"
        params = {"season": season}
        data = self._get_json(endpoint, params=params)
        if not isinstance(data, dict):
            self._standings_memo[memo_key] = []
            return []
        if data.get("errorCode") or data.get("message"):
            if competition_allowed(competition_code):
                print(f"[Football-Data.org standings] {competition_code}: {data.get('message', data)}")
            self._standings_memo[memo_key] = []
            return []
        groups = data.get("standings", []) or []
        self._standings_memo[memo_key] = groups
        return groups

    def fetch_team_position(self, team_id: int, competition_code: str, season: int) -> Dict[str, Any]:
        """Get a team's league-table row from Football-Data.org standings."""
        if not team_id or not competition_code or not football_data_requests_allowed():
            return {}
        cache_key = f"football_data_team_position_{team_id}_{competition_code}_{season}"
        cached = self.cache.get(cache_key, ttl_hours=24)
        if cached:
            return cached
        try:
            groups = self.fetch_standings(competition_code, season)
            for group in groups or []:
                if str(group.get("type") or "").upper() not in ("TOTAL", ""):
                    continue
                for entry in group.get("table") or []:
                    team = entry.get("team") or {}
                    if team.get("id") != team_id:
                        continue
                    result = {
                        "position": entry.get("position"),
                        "played": entry.get("playedGames", 0),
                        "won": entry.get("won", 0),
                        "drawn": entry.get("draw", 0),
                        "lost": entry.get("lost", 0),
                        "goals_for": entry.get("goalsFor", 0),
                        "goals_against": entry.get("goalsAgainst", 0),
                        "goal_diff": entry.get("goalDifference", 0),
                        "points": entry.get("points", 0),
                        "form": entry.get("form", ""),
                        "source": "football_data_org",
                    }
                    self.cache.set(cache_key, result, ttl_hours=12)
                    return result
        except Exception:
            pass
        return {}

    def parse_form_from_matches(self, matches: List[Dict[str, Any]]) -> Dict[str, Any]:
        form = []
        wins = 0
        draws = 0
        losses = 0
        goals_for = 0
        goals_against = 0
        btts_count = 0

        for match in matches[:10]:
            score = match.get("score", {})
            full_time = score.get("fullTime", {})
            home_goals = full_time.get("home", 0)
            away_goals = full_time.get("away", 0)

            if home_goals > away_goals:
                form.append("W")
                wins += 1
            elif home_goals < away_goals:
                form.append("L")
                losses += 1
            else:
                form.append("D")
                draws += 1

            if home_goals > 0 and away_goals > 0:
                btts_count += 1

            goals_for += home_goals
            goals_against += away_goals

        return {
            "form": "".join(reversed(form)),
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "goals_for": goals_for,
            "goals_against": goals_against,
            "btts_count": btts_count,
        }


class SportsMonkClient(BaseApiClient):
    def __init__(self, api_key: str) -> None:
        super().__init__(api_key, "https://soccer.sportmonks.com/api/v2.0", "Authorization", "sportsmonk")

    def fetch_fixtures(self, league_id: int, season_id: int) -> List[Dict[str, Any]]:
        endpoint = "fixtures"
        params = {
            "api_token": self.api_key,
            "leagues": league_id,
            "season_id": season_id,
            "include": "localTeam,visitorTeam,odds",
        }
        data = self._get_json(endpoint, params=params)
        return data.get("data", [])

    def fetch_team_stats(self, team_id: int) -> Dict[str, Any]:
        endpoint = f"teams/{team_id}"
        params = {"api_token": self.api_key}
        return self._get_json(endpoint, params=params)

    def fetch_team_matches(self, team_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        endpoint = "fixtures"
        params = {
            "api_token": self.api_key,
            "teams": team_id,
            "limit": limit,
            "sort": "-id",
        }
        data = self._get_json(endpoint, params=params)
        return data.get("data", [])


class ApiSportsFootballClient(BaseApiClient):
    def __init__(self, api_key: str) -> None:
        super().__init__(api_key, "https://v3.football.api-sports.io", "x-apisports-key", "api_sports")

    def _get_json(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
        *,
        soft_rate_limit: bool = False,
    ) -> Dict[str, Any]:
        """API-Football: validate body, avoid caching hard errors, surface rate/token issues."""
        cache_key = f"{self.service_name}_{endpoint}_{str(params)}"
        if use_cache:
            cached = self.cache.get(cache_key, ttl_hours=4)
            if cached is not None:
                return cached

        guarded = _local_guard_stale_response(self, cache_key, use_cache=use_cache)
        if guarded is not None:
            return guarded
        reason = self.rate_limiter.block_reason(self.service_name)
        if reason:
            return {"response": [], "errors": {"rate_limit": "local guard", "block_reason": reason}}

        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        try:
            response = _http_get_with_backoff(
                url,
                headers=self._get_headers(),
                params=params,
                timeout=25,
                service_label="API-Sports",
                max_retries=1 if soft_rate_limit else 3,
                max_rate_limit_wait=0.0 if soft_rate_limit else None,
            )
            if soft_rate_limit and response.status_code in (429, 503):
                log_resilience_event(
                    _api_log,
                    "provider_rate_limited",
                    service=self.service_name,
                    endpoint=endpoint,
                    status=response.status_code,
                )
                if use_cache:
                    stale = self.cache.peek(cache_key)
                    if isinstance(stale, dict):
                        return stale
                return {
                    "response": [],
                    "errors": {"rate_limit": response.status_code, "block_reason": "provider"},
                }
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            print(f"[API-Sports HTTP] {endpoint}: {exc}")
            if use_cache:
                stale = self.cache.peek(cache_key)
                if isinstance(stale, dict):
                    log_resilience_event(
                        _api_log,
                        "provider_http_stale_reuse",
                        service=self.service_name,
                        endpoint=endpoint,
                        error=str(exc)[:120],
                    )
                    return stale
            return {"response": [], "errors": {"http": str(exc), "block_reason": "provider"}}
        except ValueError as exc:
            print(f"[API-Sports JSON] {endpoint}: {exc}")
            return {"response": [], "errors": {"json": str(exc)}}

        if not isinstance(data, dict):
            print(f"[API-Sports] {endpoint}: unexpected payload type {type(data)}")
            return {"response": [], "errors": {"shape": "non-object JSON"}}

        if _api_football_errors_truthy(data.get("errors")):
            global _API_SPORTS_MISSING_KEY_WARNED
            errs = data.get("errors")
            if _api_sports_errors_indicate_missing_or_invalid_key(errs):
                if not _API_SPORTS_MISSING_KEY_WARNED:
                    _API_SPORTS_MISSING_KEY_WARNED = True
                    print(
                        "[API-Sports] Missing or invalid API key (header x-apisports-key). "
                        "Set API_SPORTS_FOOTBALL_KEY, API_SPORTS_KEY, or APISPORTS_KEY in .env. "
                        f"First error: {errs!r}"
                    )
            else:
                print(f"[API-Sports errors] {endpoint} params={params}: {errs}")
            if _api_football_daily_quota_exhausted(errs):
                try:
                    entry = self.rate_limiter._ensure_entry_shape(self.service_name)
                    entry["count"] = self.rate_limiter.limits[self.service_name]
                    from datetime import datetime, timedelta

                    entry["reset_at"] = (datetime.now() + timedelta(hours=1)).isoformat()
                    entry["minute_count"] = self.rate_limiter.minute_limits.get(self.service_name, 22)
                    entry["minute_reset_at"] = (datetime.now() + timedelta(minutes=1)).isoformat()
                    self.rate_limiter._save_state()
                    log_resilience_event(
                        _api_log,
                        "provider_daily_quota_exhausted",
                        service=self.service_name,
                        endpoint=endpoint,
                    )
                except Exception:
                    pass
                if use_cache:
                    stale = self.cache.peek(cache_key)
                    if isinstance(stale, dict):
                        return stale
            if not _api_football_rate_limited(errs):
                self.rate_limiter.record_request(self.service_name)
            return {"response": [], "errors": errs, "results": data.get("results", 0)}

        self.rate_limiter.record_request(self.service_name)
        self.cache.set(cache_key, data, ttl_hours=4)
        return data

    def fetch_injuries(self, fixture_id: int) -> List[Dict[str, Any]]:
        """Injuries / absences for a fixture (API-Football). Soft-fail on 429 so dashboard does not 500."""
        endpoint = "injuries"
        params = {"fixture": fixture_id}
        data = self._get_json(endpoint, params=params, soft_rate_limit=True)
        errs = data.get("errors")
        if _api_football_rate_limited(errs) or (
            isinstance(errs, dict) and errs.get("rate_limit") is not None
        ):
            return []
        return data.get("response", []) if isinstance(data.get("response"), list) else []

    def fetch_fixture_lineups(
        self,
        fixture_id: int,
        *,
        ttl_hours: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Confirmed lineups for a fixture (API-Football ``fixtures/lineups``).

        Uses a dedicated per-fixture cache key so TTL can track kickoff proximity
        (see ``lineup_enrich.lineup_cache_ttl_hours``).
        """
        cache_key = f"lineups_fixture_{int(fixture_id)}"
        cached = self.cache.get(cache_key, ttl_hours=ttl_hours)
        if cached is not None:
            return cached if isinstance(cached, list) else []
        data = self._get_json("fixtures/lineups", params={"fixture": int(fixture_id)}, use_cache=False)
        rows = data.get("response", []) if isinstance(data.get("response"), list) else []
        self.cache.set(cache_key, rows, ttl_hours=ttl_hours)
        return rows

    def fetch_top_scorers(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        """League top scorers (API-Football players/topscorers). Cached 24h."""
        cache_key = f"top_scorers_{league_id}_{season}"
        cached = self.cache.get(cache_key, ttl_hours=24)
        if cached is not None:
            return cached if isinstance(cached, list) else []
        endpoint = "players/topscorers"
        params = {"league": league_id, "season": season}
        data = self._get_json(endpoint, params=params, use_cache=False)
        resp = data.get("response", [])
        rows = resp if isinstance(resp, list) else []
        self.cache.set(cache_key, rows, ttl_hours=24)
        return rows

    def fetch_team_squad(
        self,
        team_id: int,
        *,
        season: Optional[int] = None,
        ttl_hours: float = 24.0,
    ) -> List[Dict[str, Any]]:
        """Current squad roster (API-Football ``players/squads``). Cached per team."""
        cache_key = f"squad_team_{int(team_id)}"
        if season is not None:
            cache_key = f"{cache_key}_{int(season)}"
        cached = self.cache.get(cache_key, ttl_hours=ttl_hours)
        if cached is not None:
            return cached if isinstance(cached, list) else []
        params: Dict[str, Any] = {"team": int(team_id)}
        data = self._get_json("players/squads", params=params, use_cache=False)
        resp = data.get("response", [])
        players: List[Dict[str, Any]] = []
        if isinstance(resp, list) and resp:
            block = resp[0] if isinstance(resp[0], dict) else {}
            raw = block.get("players")
            if isinstance(raw, list):
                players = [p for p in raw if isinstance(p, dict)]
        self.cache.set(cache_key, players, ttl_hours=ttl_hours)
        return players

    def fetch_odds(self, fixture_id: int) -> List[Dict[str, Any]]:
        endpoint = "odds"
        params = {"fixture": fixture_id}
        data = self._get_json(endpoint, params=params)
        return data.get("response", [])

    def fetch_fixture(self, fixture_id: int) -> Dict[str, Any]:
        endpoint = "fixtures"
        params = {"id": fixture_id}
        data = self._get_json(endpoint, params=params)
        return data.get("response", [{}])[0] if data.get("response") else {}

    def fetch_fixture_statistics(
        self,
        fixture_id: int,
        *,
        ttl_hours: float = 12.0,
    ) -> List[Dict[str, Any]]:
        """Post-match / live statistics (Expected Goals when provider supplies them)."""
        cache_key = f"api_sports_fixture_stats_{int(fixture_id)}"
        cached = self.cache.get(cache_key, ttl_hours=ttl_hours)
        if isinstance(cached, list):
            return cached
        data = self._get_json("fixtures/statistics", params={"fixture": int(fixture_id)})
        resp = data.get("response")
        out = resp if isinstance(resp, list) else []
        self.cache.set(cache_key, out, ttl_hours=ttl_hours)
        return out

    def fetch_fixtures_by_league(
        self,
        league_id: int,
        season: int,
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        endpoint = "fixtures"
        params: Dict[str, Any] = {"league": league_id, "season": season}
        if status:
            params["status"] = status
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to
        data = self._get_json(endpoint, params=params)
        resp = data.get("response", [])
        return resp if isinstance(resp, list) else []

    def fetch_fixtures_by_date(
        self,
        date: str,
        *,
        league_id: Optional[int] = None,
        season: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """All fixtures on a calendar day (optional league filter) — used for audit settlement repair."""
        params: Dict[str, Any] = {"date": date}
        if league_id is not None:
            params["league"] = int(league_id)
        if season is not None:
            params["season"] = int(season)
        data = self._get_json("fixtures", params=params)
        resp = data.get("response", [])
        return resp if isinstance(resp, list) else []

    def resolve_team_id_by_name(self, team_name: str) -> Optional[int]:
        """Map display name → API-Football team id (cached). Used when fixtures carry FotMob/FDO ids."""
        from hibs_predictor.team_aliases import canonical_team_key, team_names_match

        name = (team_name or "").strip()
        if len(name) < 3:
            return None
        nk = canonical_team_key(name)
        if not nk or len(nk) < 3:
            return None
        cache_key = f"api_team_resolve_{nk}"
        cached = self.cache.get(cache_key, ttl_hours=168.0)
        if cached is not None:
            try:
                tid = int(cached)
                return tid if tid > 0 else None
            except (TypeError, ValueError):
                return None

        queries: List[str] = []
        for candidate in (name, name.split()[-1] if " " in name else ""):
            q = (candidate or "").strip()
            if len(q) >= 3 and q not in queries:
                queries.append(q)

        resolved: Optional[int] = None
        for query in queries:
            data = self._get_json("teams", params={"search": query})
            for block in data.get("response") or []:
                if not isinstance(block, dict):
                    continue
                team = block.get("team") or {}
                if not isinstance(team, dict):
                    continue
                nm = str(team.get("name") or "")
                if team_names_match(nm, name):
                    try:
                        resolved = int(team.get("id"))
                    except (TypeError, ValueError):
                        resolved = None
                    if resolved and resolved > 0:
                        break
            if resolved:
                break

        self.cache.set(cache_key, resolved or 0, ttl_hours=168.0)
        return resolved

    def fetch_team_last_matches(self, team_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Last *finished* league/cup matches for this team (scores present)."""
        endpoint = "fixtures"
        params = {"team": team_id, "last": limit, "status": "FT"}
        data = self._get_json(endpoint, params=params)
        return data.get("response", [])

    def fetch_team_statistics(self, team_id: int, season: int, league_id: int = None) -> Dict[str, Any]:
        endpoint = "teams/statistics"
        params = {"team": team_id, "season": season}
        if league_id:
            params["league"] = league_id
        data = self._get_json(endpoint, params=params)
        return data.get("response", {})

    def fetch_standings(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        endpoint = "standings"
        params = {"league": league_id, "season": season}
        data = self._get_json(endpoint, params=params)
        standings = data.get("response", [])
        return standings[0].get("league", {}).get("standings", [[]]) if standings else [[]]

    def fetch_team_position(self, team_id: int, league_id: int, season: int) -> Dict[str, Any]:
        """Get a team's current league position and stats."""
        cache_key = f"team_position_{team_id}_{league_id}_{season}"
        cached = self.cache.get(cache_key, ttl_hours=6)
        if cached:
            return cached
        try:
            all_standings = self.fetch_standings(league_id, season)
            for group in all_standings:
                for entry in group:
                    if entry.get("team", {}).get("id") == team_id:
                        result = {
                            "position": entry.get("rank", "?"),
                            "played": entry.get("all", {}).get("played", 0),
                            "won": entry.get("all", {}).get("win", 0),
                            "drawn": entry.get("all", {}).get("draw", 0),
                            "lost": entry.get("all", {}).get("lose", 0),
                            "goals_for": entry.get("all", {}).get("goals", {}).get("for", 0),
                            "goals_against": entry.get("all", {}).get("goals", {}).get("against", 0),
                            "goal_diff": entry.get("goalsDiff", 0),
                            "points": entry.get("points", 0),
                            "form": entry.get("form", ""),
                            "source": "api_sports",
                        }
                        self.cache.set(cache_key, result, ttl_hours=6)
                        return result
        except Exception:
            pass
        return {}


class OddsApiClient(BaseApiClient):
    # Map our league codes to The Odds API v4 sport keys (see https://the-odds-api.com/liveapi/guides/v4/)
    SPORT_KEYS = {
        "EPL": "soccer_epl",
        "CHAMPIONSHIP": "soccer_efl_champ",
        "LEAGUE_ONE": "soccer_england_league1",
        "LEAGUE_TWO": "soccer_england_league2",
        "FA_CUP": "soccer_fa_cup",
        "LEAGUE_CUP": "soccer_england_efl_cup",
        "IRELAND_PREMIER": "soccer_league_of_ireland",
        "SCOTTISH_CUP": "soccer_scotland_cup",
        "COPA_DEL_REY": "soccer_spain_copa_del_rey",
        "COPPA_ITALIA": "soccer_italy_coppa_italia",
        "COUPE_DE_FRANCE": "soccer_france_coupe_de_france",
        "DFB_POKAL": "soccer_germany_dfb_pokal",
        "SCOTLAND": "soccer_spl",
        "SCOTLAND_CHAMP": "soccer_scotland_championship",
        "UCL": "soccer_uefa_champs_league",
        "EUROPA_LEAGUE": "soccer_uefa_europa_league",
        "UECL": "soccer_uefa_europa_conference_league",
        "LA_LIGA": "soccer_spain_la_liga",
        "SERIE_A": "soccer_italy_serie_a",
        "BUNDESLIGA": "soccer_germany_bundesliga",
        "LIGUE_1": "soccer_france_ligue_one",
        "EREDIVISIE": "soccer_netherlands_eredivisie",
        "PRIMEIRA": "soccer_portugal_primeira_liga",
        "BELGIUM_FIRST": "soccer_belgium_first_div",
        "DENMARK_SL": "soccer_denmark_superliga",
        "GREECE_SL": "soccer_greece_super_league",
        "AUSTRIA_BL": "soccer_austria_bundesliga",
        "NORWAY_ELITESERIEN": "soccer_norway_eliteserien",
        "FINLAND_VEIKKAUSLIIGA": "soccer_finland_veikkausliiga",
        "WORLD_CUP": "soccer_fifa_world_cup",
        "EUROS": "soccer_uefa_european_championship",
        "NATIONS_LEAGUE": "soccer_uefa_nations_league",
        "INTL_FRIENDLIES": "soccer_international_friendlies",
    }
    # Legacy / alternate keys tried when the primary sport returns HTTP 404.
    SPORT_KEY_FALLBACKS: Dict[str, List[str]] = {
        "CHAMPIONSHIP": ["soccer_england_efl_championship"],
        "SCOTLAND": ["soccer_scotland_premiership"],
        "INTL_FRIENDLIES": ["soccer_fifa_world_cup"],
        "LEAGUE_CUP": ["soccer_efl_league_cup"],
        "SCOTTISH_CUP": ["soccer_scotland_league_cup"],
        "COPA_DEL_REY": ["soccer_spain_copa_del_rey"],
        "COPPA_ITALIA": ["soccer_italy_copa_italia"],
    }

    def __init__(self, api_key: str) -> None:
        super().__init__(api_key, "https://api.the-odds-api.com/v4", "Authorization", "odds_api")

    def _get_headers(self) -> Dict[str, str]:
        return {}  # OddsAPI uses apiKey as query param

    def fetch_odds_for_league(self, league_code: str) -> List[Dict[str, Any]]:
        """Fetch all upcoming odds for a league. Returns list of events with bookmaker odds."""
        sport_key = self.SPORT_KEYS.get(league_code)
        if not sport_key:
            return []
        cache_key = f"odds_api_league_{league_code}"
        cached = self.cache.get(cache_key, ttl_hours=1)
        if cached is not None:
            return cached
        keys_to_try = [sport_key] + [
            k for k in self.SPORT_KEY_FALLBACKS.get(league_code, []) if k != sport_key
        ]
        import requests as _req

        params = {
            "apiKey": self.api_key,
            "regions": "uk",
            "markets": "h2h,totals,btts",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }
        for key in keys_to_try:
            try:
                url = f"{self.base_url}/sports/{key}/odds"
                resp = _req.get(url, params=params, timeout=15)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                data = resp.json()
                out = data if isinstance(data, list) else []
                self.cache.set(cache_key, out, ttl_hours=1)
                return out
            except Exception:
                continue
        return []

    def fetch_live_odds(self, league_key: str = "soccer_epl") -> List[Dict[str, Any]]:
        endpoint = f"sports/{league_key}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": "uk,eu",
            "markets": "h2h,totals,btts",
            "oddsFormat": "decimal",
        }
        try:
            url = f"{self.base_url}/{endpoint}"
            import requests as _req
            resp = _req.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception:
            return []


class StatsApiClient(BaseApiClient):
    def __init__(self, api_key: str) -> None:
        super().__init__(api_key, "https://v1.api-football.com", "x-rapidapi-key", "stats_api")

    def fetch_team_stats(self, team_id: int, season: int) -> Dict[str, Any]:
        endpoint = "teams/statistics"
        params = {"team": team_id, "season": season}
        return self._get_json(endpoint, params=params)

    def fetch_team_form(self, team_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        endpoint = "fixtures"
        params = {"team": team_id, "last": limit, "status": "FT"}
        data = self._get_json(endpoint, params=params)
        return data.get("response", [])

    def fetch_xg_data(self, fixture_id: int) -> Dict[str, Any]:
        endpoint = f"fixtures/statistics/{fixture_id}"
        return self._get_json(endpoint)
