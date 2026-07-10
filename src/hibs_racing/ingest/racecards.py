from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from hibs_racing.cards.enrich import parse_runner_row_enrich
from hibs_racing.cards.form_parser import parse_form_string
from hibs_racing.config import ROOT
from hibs_racing.ingest.scrape import _load_env, ensure_rpscrape, ensure_rpscrape_deps

RPSCRAPE_RACECARDS = ROOT / "vendor" / "rpscrape" / "racecards"
RPSCRAPE_ROOT = ROOT / "vendor" / "rpscrape"


def _sync_rpscrape_dotenv() -> dict[str, str]:
    """Load hibs-racing .env and pass EMAIL/ACCESS_TOKEN into the rpscrape subprocess."""
    env = _load_env() or os.environ.copy()
    email = env.get("EMAIL", "").strip()
    token = env.get("ACCESS_TOKEN", "").strip()
    if email and token:
        # rpscrape README: credentials live in repo root .env
        rp_env = RPSCRAPE_ROOT / ".env"
        rp_env.write_text(f"EMAIL={email}\nACCESS_TOKEN={token}\n", encoding="utf-8")
    return env


def fetch_racecards(
    *,
    day: int | None = None,
    days: int | None = None,
    region: str = "gb",
    timeout_sec: int = 120,
) -> list[Path]:
    """
    Fetch racecards via vendor rpscrape racecards.py.

    Uses --day N (single day) or --days N (today through N days). Requires Python 3.13+
    in vendor rpscrape; set EMAIL + ACCESS_TOKEN in ~/hibs-racing/.env if RP blocks you.
    """
    if day is not None and days is not None:
        raise ValueError("Use either day= or days=, not both")
    scripts = ensure_rpscrape()
    ensure_rpscrape_deps()
    RPSCRAPE_RACECARDS.mkdir(parents=True, exist_ok=True)

    if days is not None:
        cmd = [sys.executable, "racecards.py", "--days", str(days), "--region", region]
        target_dates = [(date.today() + timedelta(days=i)).isoformat() for i in range(days)]
    else:
        d = day if day is not None else 1
        cmd = [sys.executable, "racecards.py", "--day", str(d), "--region", region]
        target_dates = [(date.today() + timedelta(days=d - 1)).isoformat()]

    env = _sync_rpscrape_dotenv()
    if not env.get("EMAIL") or not env.get("ACCESS_TOKEN"):
        print(
            "Note: no EMAIL/ACCESS_TOKEN in .env — RP may rate-limit. "
            "See README → rpscrape auth.",
            file=sys.stderr,
        )

    result = subprocess.run(
        cmd,
        cwd=scripts,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout_sec,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"racecards fetch failed:\n{result.stdout}\n{result.stderr}\n"
            "Add Racing Post credentials to .env (EMAIL + ACCESS_TOKEN), "
            "or import a CSV: hibs-racing ingest-cards data/samples/cards_template.csv"
        )

    paths: list[Path] = []
    for target_date in target_dates:
        out = RPSCRAPE_RACECARDS / f"{target_date}.json"
        if out.exists():
            paths.append(out)
    if not paths:
        candidates = sorted(RPSCRAPE_RACECARDS.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            raise RuntimeError("No racecard JSON written — RP may be blocking.")
        paths = candidates[-len(target_dates) :]
    return paths


def fetch_racecards_on_date(
    card_date: str,
    *,
    region: str | None = None,
    timeout_sec: int = 300,
) -> Path | None:
    """
    Fetch RP racecards for an absolute calendar date (not day-offset from today).
    Uses API-only historical path (meetings + cardrunners + free-stats-tab).
    """
    from hibs_racing.ingest.historical_racecards import fetch_historical_racecards_on_date

    regions = (region.lower(),) if region else ("gb", "ire")
    return fetch_historical_racecards_on_date(
        card_date,
        regions=regions,
        timeout_sec=timeout_sec,
    )


def load_racecard_frames(*, day: int | None = None, days: int | None = None, region: str = "gb") -> pd.DataFrame:
    """Fetch + parse racecard JSON into a single runner-level frame."""
    json_paths = fetch_racecards(day=day, days=days, region=region)
    frames = [parse_racecard_json(path) for path in json_paths]
    if len(frames) == 1:
        return frames[0]
    return pd.concat(frames, ignore_index=True)


def _parse_trainer_14_days(raw: object) -> tuple[int | None, int | None]:
    if not isinstance(raw, dict):
        return None, None
    wins = raw.get("wins") or raw.get("winners") or raw.get("totalWinners")
    runs = raw.get("runs") or raw.get("runners") or raw.get("totalRunners")
    try:
        w = int(wins) if wins is not None else None
        r = int(runs) if runs is not None else None
        return w, r
    except (TypeError, ValueError):
        return None, None


def _parse_trainer_rtf(raw: object) -> float | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    text = str(raw).strip().replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_racecard_json(json_path: Path) -> pd.DataFrame:
    """Flatten rpscrape nested racecards JSON → runner rows."""
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    card_date = json_path.stem

    for _region, courses in payload.items():
        if not isinstance(courses, dict):
            continue
        for course, times in courses.items():
            if not isinstance(times, dict):
                continue
            for off_time, race in times.items():
                if not isinstance(race, dict):
                    continue
                race_id = str(race.get("race_id") or f"{card_date}_{course}_{off_time}")
                runners = race.get("runners") or []
                for runner in runners:
                    if not isinstance(runner, dict):
                        continue
                    if runner.get("non_runner") or runner.get("reserve"):
                        continue
                    horse = runner.get("name") or ""
                    horse_id = str(runner.get("horse_id") or horse)
                    t14_w, t14_r = _parse_trainer_14_days(runner.get("trainer_14_days"))
                    row = {
                            "race_id": race_id,
                            "card_date": race.get("date") or card_date,
                            "off_time": race.get("off_time") or off_time,
                            "course": race.get("course") or course,
                            "region": race.get("region") or _region,
                            "race_name": race.get("race_name"),
                            "race_type": race.get("race_type"),
                            "race_class": str(race.get("race_class") or ""),
                            "going": race.get("going"),
                            "distance_f": race.get("distance_f"),
                            "field_size": race.get("field_size") or len(runners),
                            "horse_id": horse_id,
                            "horse_name": horse,
                            "draw": runner.get("draw"),
                            "official_rating": runner.get("ofr"),
                            "rpr": runner.get("rpr"),
                            "jockey": runner.get("jockey"),
                            "trainer": runner.get("trainer"),
                            "days_since_last_run": runner.get("last_run"),
                            "card_comment": runner.get("comment") or runner.get("spotlight") or "",
                            "rp_verdict": race.get("rp_verdict"),
                            "form_string": runner.get("form") or "",
                            "trainer_rtf": _parse_trainer_rtf(runner.get("trainer_rtf")),
                            "trainer_14d_wins": t14_w,
                            "trainer_14d_runs": t14_r,
                            "trainer_location": runner.get("trainer_location"),
                        }
                    row.update(parse_runner_row_enrich(runner))
                    row.update(
                        parse_form_string(
                            row.get("form_string"),
                            today_distance_f=row.get("distance_f"),
                        )
                    )
                    rows.append(row)

    if not rows:
        raise ValueError(f"No runners parsed from {json_path}")
    frame = pd.DataFrame(rows)
    frame["runner_id"] = (
        frame["race_id"].astype(str)
        + ":"
        + frame["horse_name"].str.lower().str.replace(r"\s+", "_", regex=True)
    )
    return frame


def normalize_cards_csv(frame: pd.DataFrame) -> pd.DataFrame:
    """Manual CSV fallback — required: race_id, card_date, horse_name; optional jockey, trainer, or, rpr, draw."""
    colmap = {c.lower(): c for c in frame.columns}
    def col(*names: str) -> str | None:
        for n in names:
            if n in frame.columns:
                return n
            if n.lower() in colmap:
                return colmap[n.lower()]
        return None

    race_col = col("race_id")
    date_col = col("card_date", "date")
    horse_col = col("horse_name", "horse")
    if not race_col or not date_col or not horse_col:
        raise ValueError("CSV needs race_id, card_date (or date), horse_name (or horse)")

    out = pd.DataFrame()
    out["race_id"] = frame[race_col].astype(str)
    out["card_date"] = pd.to_datetime(frame[date_col]).dt.strftime("%Y-%m-%d")
    out["horse_name"] = frame[horse_col].astype(str).str.strip()
    out["horse_id"] = frame[col("horse_id")] if col("horse_id") else out["horse_name"]
    for src, dst in (
        ("off_time", "off_time"),
        ("course", "course"),
        ("jockey", "jockey"),
        ("trainer", "trainer"),
        ("draw", "draw"),
        ("or", "official_rating"),
        ("official_rating", "official_rating"),
        ("rpr", "rpr"),
        ("race_class", "race_class"),
        ("going", "going"),
        ("field_size", "field_size"),
        ("distance_f", "distance_f"),
        ("dist_f", "distance_f"),
    ):
        c = col(src)
        if c:
            out[dst if dst != "official_rating" or src != "or" else "official_rating"] = frame[c]
    out["runner_id"] = (
        out["race_id"] + ":" + out["horse_name"].str.lower().str.replace(r"\s+", "_", regex=True)
    )
    return out
