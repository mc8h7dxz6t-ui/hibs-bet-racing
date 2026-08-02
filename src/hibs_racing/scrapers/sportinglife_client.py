"""Sporting Life — results/SP backup when Racing Post scrape is thin or blocked.

Optional settlement enricher; off by default (HIBS_ENABLE_SPORTINGLIFE_BACKUP=1).
"""

from __future__ import annotations

import os
import re
from datetime import date
from typing import Any, Dict, List, Optional

import requests

_BASE = "https://www.sportinglife.com"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; hibs-racing/1.0)",
    "Accept": "text/html,application/json",
}


def sportinglife_enabled() -> bool:
    return (os.getenv("HIBS_ENABLE_SPORTINGLIFE_BACKUP") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _get(url: str, *, timeout: int = 20) -> requests.Response:
    return requests.get(url, headers=_HEADERS, timeout=timeout)


def probe_availability() -> Dict[str, Any]:
    try:
        resp = _get(f"{_BASE}/racing/results", timeout=12)
        ok = resp.status_code == 200 and len(resp.text or "") > 500
        return {"ok": ok, "status": resp.status_code, "bytes": len(resp.text or "")}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


def fetch_results_html(card_date: Optional[str] = None) -> str:
    """Fetch results index HTML for a calendar day (YYYY-MM-DD)."""
    day = (card_date or date.today().isoformat())[:10]
    url = f"{_BASE}/racing/results/{day}"
    resp = _get(url)
    if resp.status_code == 404:
        resp = _get(f"{_BASE}/racing/results")
    resp.raise_for_status()
    return resp.text


def _parse_fractional_sp(text: str) -> Optional[float]:
    text = (text or "").strip().upper()
    if not text or text in ("SP", "NR", "-"):
        return None
    m = re.match(r"^(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)$", text)
    if m:
        num, den = float(m.group(1)), float(m.group(2))
        if den > 0:
            return 1.0 + num / den
    try:
        val = float(text)
        return val if val > 1.0 else None
    except ValueError:
        return None


def parse_results_from_html(html: str, *, card_date: str) -> List[Dict[str, Any]]:
    """Best-effort parse — extracts course/time/horse/SP tuples from results HTML."""
    rows: List[Dict[str, Any]] = []
    if not html:
        return rows
    # Lightweight pattern: horse name near fractional SP in result cards.
    for block in re.split(r"<article", html, flags=re.I)[1:]:
        horse_m = re.search(r'class="[^"]*horse[^"]*"[^>]*>([^<]+)<', block, flags=re.I)
        sp_m = re.search(r'class="[^"]*price[^"]*"[^>]*>([^<]+)<', block, flags=re.I)
        course_m = re.search(r'data-course="([^"]+)"', block, flags=re.I)
        if not horse_m:
            continue
        sp = _parse_fractional_sp(sp_m.group(1) if sp_m else "")
        rows.append(
            {
                "card_date": card_date,
                "course": (course_m.group(1) if course_m else "").strip(),
                "horse_name": horse_m.group(1).strip(),
                "sp_decimal": sp,
                "source": "sportinglife_html",
            }
        )
    return rows


def fetch_results_for_date(card_date: Optional[str] = None) -> List[Dict[str, Any]]:
    if not sportinglife_enabled():
        return []
    day = (card_date or date.today().isoformat())[:10]
    try:
        html = fetch_results_html(day)
        return parse_results_from_html(html, card_date=day)
    except Exception:
        return []
