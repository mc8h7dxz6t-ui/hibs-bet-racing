"""Retain best on-disk fixture bundle — never destroy a good cache for enrich gaps.

Policy (personal research stack):
- Keep the most recent bundle with fixtures on disk when enrich/odds coverage is low.
- Only replace when a new fetch has strictly higher quality score OR cache is empty/stale.
- Never treat low enrich alone as cache_miss — thin listings are valid if odds are not fabricated.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "")
    if not raw:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def bundle_quality_score(bundle: Dict[str, Any]) -> float:
    """Higher is better — used to compare candidate vs incumbent on disk."""
    rows = bundle.get("all") or []
    if not rows:
        return 0.0
    n = len(rows)
    enrich = 0
    odds = 0
    dq_sum = 0.0
    dq_n = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        dq = row.get("data_quality") or {}
        if isinstance(dq, dict):
            pct = dq.get("score_pct")
            if pct is not None:
                try:
                    dq_sum += float(pct)
                    dq_n += 1
                except (TypeError, ValueError):
                    pass
            if dq.get("full_scope"):
                enrich += 1
        bo = row.get("best_odds_1x2") or {}
        if isinstance(bo, dict) and any(bo.get(k) for k in ("home", "draw", "away")):
            odds += 1
    avg_dq = dq_sum / dq_n if dq_n else 0.0
    enrich_pct = 100.0 * enrich / n
    odds_pct = 100.0 * odds / n
    # Weight: fixture count, DQ, enrich, real odds (never reward empty odds as quality)
    return round(n * 10.0 + avg_dq * 0.5 + enrich_pct * 0.3 + odds_pct * 0.8, 2)


def disk_bundle_snapshot(*, include_domestic: bool = False) -> Dict[str, Any]:
    """Peek current on-disk bundle without network fetch."""
    try:
        from hibs_predictor.cache import Cache
        from hibs_predictor.web import _all_fixtures_cache_key

        peek = Cache().peek(_all_fixtures_cache_key(include_domestic=include_domestic))
        if not isinstance(peek, dict):
            return {"present": False, "fixture_count": 0, "quality_score": 0.0}
        rows = peek.get("all") or []
        return {
            "present": bool(rows),
            "fixture_count": len(rows),
            "quality_score": bundle_quality_score(peek),
            "bundle": peek,
        }
    except Exception as exc:
        return {"present": False, "fixture_count": 0, "quality_score": 0.0, "error": str(exc)[:120]}


def should_preserve_disk_bundle(
    *,
    football_bundle_ok: Optional[bool] = None,
    fixture_count: Optional[int] = None,
) -> bool:
    """True when repair must NOT bust/wipe fixture cache."""
    if _env_truthy("HIBS_FORCE_CACHE_BUST"):
        return False
    if _env_truthy("HIBS_PRESERVE_GREEN_CACHE", default=True):
        snap = disk_bundle_snapshot()
        fc = fixture_count if fixture_count is not None else int(snap.get("fixture_count") or 0)
        if fc > 0:
            return True
        if football_bundle_ok is True and fc > 0:
            return True
    return False


def should_replace_bundle(incumbent: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
    """Only overwrite disk when candidate is strictly better or incumbent empty."""
    inc_rows = incumbent.get("all") or []
    cand_rows = candidate.get("all") or []
    if not inc_rows:
        return bool(cand_rows)
    if not cand_rows:
        return False
    inc_q = bundle_quality_score(incumbent)
    cand_q = bundle_quality_score(candidate)
    # Require measurable improvement — avoid churn on scrape-first thin days
    min_delta = float(os.getenv("HIBS_CACHE_REPLACE_MIN_DELTA", "2.0"))
    return cand_q >= inc_q + min_delta
