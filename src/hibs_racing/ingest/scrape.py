from __future__ import annotations

import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from hibs_racing.ingest.rate_limit import rp_scrape_day_pause

ROOT = Path(__file__).resolve().parents[3]
RPSCRAPE_DIR = ROOT / "vendor" / "rpscrape"
RPSCRAPE_SCRIPTS = RPSCRAPE_DIR / "scripts"
RPSCRAPE_REPO = "https://github.com/joenano/rpscrape.git"

# A valid day file has header + many runners; partial/empty files are re-scraped.
MIN_DAY_CSV_BYTES = 8_000
MIN_DAY_CSV_LINES = 40
DAY_JOB_TIMEOUT_SEC = 90  # fail fast if RP hangs

RPSCRAPE_DEPS = (
    "curl_cffi",
    "jarowinkler",
    "lxml",
    "orjson",
    "python-dotenv",
    "tomli",
    "tqdm",
)


def ensure_rpscrape() -> Path:
    if not RPSCRAPE_SCRIPTS.exists():
        RPSCRAPE_DIR.parent.mkdir(parents=True, exist_ok=True)
        print(f"Cloning rpscrape into {RPSCRAPE_DIR} ...")
        subprocess.run(
            ["git", "clone", "--depth", "1", RPSCRAPE_REPO, str(RPSCRAPE_DIR)],
            check=True,
        )
    return RPSCRAPE_SCRIPTS


def ensure_rpscrape_deps() -> None:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", *RPSCRAPE_DEPS, "-q"],
        check=True,
    )


def _load_env() -> dict[str, str] | None:
    dotenv = ROOT / ".env"
    if not dotenv.exists():
        return None
    import os

    from dotenv import load_dotenv

    load_dotenv(dotenv)
    return os.environ.copy()


def _format_rp_date(d: date) -> str:
    return d.strftime("%Y/%m/%d")


def _format_rp_range(start: date, end: date) -> str:
    if start == end:
        return _format_rp_date(start)
    return f"{_format_rp_date(start)}-{_format_rp_date(end)}"


def rpscrape_data_dir(region: str, race_type: str) -> Path:
    return RPSCRAPE_DIR / "data" / "region" / region / race_type


def day_csv_path(day: date, region: str, race_type: str) -> Path:
    return rpscrape_data_dir(region, race_type) / f"{day.strftime('%Y_%m_%d')}.csv"


def is_valid_day_csv(path: Path) -> bool:
    """Reject empty or partial scrapes (Racing Post 429 often causes these)."""
    if not path.exists():
        return False
    try:
        size = path.stat().st_size
        if size < MIN_DAY_CSV_BYTES:
            return False
        lines = sum(1 for _ in path.open(encoding="utf-8", errors="ignore"))
        return lines >= MIN_DAY_CSV_LINES
    except OSError:
        return False


def invalidate_day_csv(day: date, region: str, race_type: str) -> None:
    path = day_csv_path(day, region, race_type)
    if path.exists() and not is_valid_day_csv(path):
        path.unlink(missing_ok=True)


def collect_csvs_in_range(
    start: date,
    end: date,
    *,
    region: str = "gb",
    race_type: str = "flat",
) -> list[Path]:
    """All per-day rpscrape CSVs that exist for [start, end]."""
    root = rpscrape_data_dir(region, race_type)
    if not root.exists():
        return []
    out: list[Path] = []
    day = start
    while day <= end:
        path = day_csv_path(day, region, race_type)
        if path.exists() and path.stat().st_size > 100:
            out.append(path)
        day += timedelta(days=1)
    return out


def collect_valid_csvs_in_range(
    start: date,
    end: date,
    *,
    region: str = "gb",
    race_type: str = "flat",
) -> list[Path]:
    """Only complete day files — skips empty/partial cache."""
    return [
        p
        for p in collect_csvs_in_range(start, end, region=region, race_type=race_type)
        if is_valid_day_csv(p)
    ]


def _invoke_rpscrape(
    *,
    start: date,
    end: date,
    region: str,
    race_type: str,
    clean: bool,
) -> subprocess.CompletedProcess[str]:
    scripts = ensure_rpscrape()
    ensure_rpscrape_deps()
    cmd = [
        sys.executable,
        "rpscrape.py",
        "-d",
        _format_rp_range(start, end),
        "-r",
        region,
        "-t",
        race_type,
    ]
    if clean:
        cmd.append("--clean")
    return subprocess.run(
        cmd,
        cwd=scripts,
        capture_output=True,
        text=True,
        env=_load_env(),
        timeout=DAY_JOB_TIMEOUT_SEC,
    )


def run_rpscrape(
    *,
    start: date,
    end: date,
    region: str = "gb",
    race_type: str = "flat",
    clean: bool = False,
    chunk_days: int = 1,
    pause_seconds: float | None = None,
    max_retries: int = 0,
    skip_existing: bool = True,
) -> list[Path]:
    """
    Scrape Racing Post results via rpscrape.

    Large ranges are split into single-day jobs so one timeout does not lose 30 days.
    Already-scraped days are skipped unless clean=True.
    """
    if pause_seconds is None:
        pause_seconds = rp_scrape_day_pause()
    if chunk_days < 1:
        raise ValueError("chunk_days must be >= 1")

    if (end - start).days + 1 <= chunk_days and not skip_existing:
        return _run_single_chunk(
            start=start,
            end=end,
            region=region,
            race_type=race_type,
            clean=clean,
        )

    failed: list[str] = []
    day = start
    while day <= end:
        chunk_end = min(day + timedelta(days=chunk_days - 1), end)
        label = _format_rp_range(day, chunk_end)

        if skip_existing and not clean:
            span = _date_span(day, chunk_end)
            missing = [
                d
                for d in span
                if not is_valid_day_csv(day_csv_path(d, region, race_type))
            ]
            if not missing:
                print(f"Skip (cached): {label}")
                day = chunk_end + timedelta(days=1)
                continue
            if len(missing) < len(span):
                for d in missing:
                    invalidate_day_csv(d, region, race_type)
                    if not _scrape_one_day_with_retry(
                        d, region=region, race_type=race_type, clean=False, max_retries=max_retries
                    ):
                        failed.append(d.isoformat())
                    if pause_seconds > 0:
                        time.sleep(pause_seconds * 3)
                day = chunk_end + timedelta(days=1)
                continue

        ok = False
        for attempt in range(1, max_retries + 2):
            print(f"Scrape {label} (attempt {attempt}) ...")
            try:
                result = _invoke_rpscrape(
                    start=day,
                    end=chunk_end,
                    region=region,
                    race_type=race_type,
                    clean=clean and attempt == 1,
                )
            except subprocess.TimeoutExpired:
                invalidate_day_csv(day, region, race_type)
                print(f"  failed: timed out after {DAY_JOB_TIMEOUT_SEC}s (Racing Post blocked or slow)")
                break
            if result.returncode == 0 and _chunk_csv_valid(day, chunk_end, region, race_type):
                if result.stdout.strip():
                    print(result.stdout.strip())
                ok = True
                break
            err = (result.stdout or "") + (result.stderr or "")
            print(f"  failed: {err.strip()[:240]}")
            if attempt <= max_retries:
                time.sleep(min(5.0, pause_seconds * 2))

        if not ok:
            if chunk_days == 1:
                failed.append(day.isoformat())
            else:
                for d in _date_span(day, chunk_end):
                    if not _scrape_one_day_with_retry(
                        d, region=region, race_type=race_type, clean=False, max_retries=1
                    ):
                        failed.append(d.isoformat())
                    if pause_seconds > 0:
                        time.sleep(pause_seconds)

        day = chunk_end + timedelta(days=1)
        if pause_seconds > 0 and day <= end:
            time.sleep(pause_seconds)

    files = collect_valid_csvs_in_range(start, end, region=region, race_type=race_type)
    if failed:
        print(
            f"Warning: {len(failed)} day(s) failed (Racing Post may be rate-limiting).\n"
            f"  Failed: {', '.join(failed[:8])}" + (" ..." if len(failed) > 8 else "") + "\n"
            "  Wait 30–60 min or add EMAIL + ACCESS_TOKEN to .env, then re-run — completed days are kept."
        )
    if not files:
        cached = collect_all_valid_csvs(region, race_type)
        if cached:
            print(
                "Live scrape produced no valid files — use cached data:\n"
                "  hibs-racing scrape --from-cache --pipeline"
            )
            return cached
        raise RuntimeError(
            "No scrape output and no cache on disk.\n"
            "Racing Post is rate-limiting or timed out.\n"
            "Wait 24h, add EMAIL + ACCESS_TOKEN to .env, or import a CSV manually."
        )
    return files


def _chunk_csv_valid(day: date, chunk_end: date, region: str, race_type: str) -> bool:
    return all(is_valid_day_csv(day_csv_path(d, region, race_type)) for d in _date_span(day, chunk_end))


def _date_span(start: date, end: date) -> list[date]:
    days: list[date] = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return days


def _scrape_one_day_with_retry(
    day: date,
    *,
    region: str,
    race_type: str,
    clean: bool,
    max_retries: int,
) -> bool:
    invalidate_day_csv(day, region, race_type)
    if is_valid_day_csv(day_csv_path(day, region, race_type)):
        return True
    label = _format_rp_date(day)
    for attempt in range(1, max_retries + 2):
        print(f"Scrape {label} (attempt {attempt}) ...")
        try:
            result = _invoke_rpscrape(
                start=day,
                end=day,
                region=region,
                race_type=race_type,
                clean=clean,
            )
        except subprocess.TimeoutExpired:
            invalidate_day_csv(day, region, race_type)
            print(f"  failed: timed out after {DAY_JOB_TIMEOUT_SEC}s")
            break
        if result.returncode == 0 and is_valid_day_csv(day_csv_path(day, region, race_type)):
            if result.stdout.strip():
                print(result.stdout.strip())
            return True
        invalidate_day_csv(day, region, race_type)
        err = ((result.stdout or "") + (result.stderr or "")).strip()
        if err:
            print(f"  failed: {err[:240]}")
        if attempt <= max_retries:
            time.sleep(2)
    return False


def _run_single_chunk(
    *,
    start: date,
    end: date,
    region: str,
    race_type: str,
    clean: bool,
) -> list[Path]:
    before = time.time()
    result = _invoke_rpscrape(
        start=start,
        end=end,
        region=region,
        race_type=race_type,
        clean=clean,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "rpscrape failed:\n"
            f"{result.stdout}\n{result.stderr}\n"
            "Network timeout — retry with fewer days: hibs-racing scrape --days 3 --pipeline\n"
            "Or add EMAIL + ACCESS_TOKEN to .env if you see 406/rate limits."
        )
    if result.stdout.strip():
        print(result.stdout.strip())

    data_root = rpscrape_data_dir(region, race_type)
    files = sorted(
        (p for p in data_root.glob("*.csv") if p.stat().st_mtime >= before - 2),
        key=lambda p: p.stat().st_mtime,
    )
    return files or collect_csvs_in_range(start, end, region=region, race_type=race_type)


def collect_all_valid_csvs(region: str = "gb", race_type: str = "flat") -> list[Path]:
    """Any complete rpscrape CSV on disk (single-day or range files)."""
    root = rpscrape_data_dir(region, race_type)
    if not root.exists():
        return []
    out = [p for p in sorted(root.glob("*.csv")) if is_valid_day_csv(p) and not p.name.startswith("hibs_")]
    return out


def scrape_days(
    *,
    days: int = 7,
    end: date | None = None,
    region: str = "gb",
    race_type: str = "flat",
    clean: bool = False,
    chunk_days: int = 1,
    pause_seconds: float = 2.0,
) -> list[Path]:
    """Scrape N calendar days ending at `end` (default: yesterday). One day per job."""
    if days < 1:
        raise ValueError("days must be >= 1")
    end_date = end or (date.today() - timedelta(days=1))
    start_date = end_date - timedelta(days=days - 1)
    return run_rpscrape(
        start=start_date,
        end=end_date,
        region=region,
        race_type=race_type,
        clean=clean,
        chunk_days=chunk_days,
        pause_seconds=pause_seconds,
    )
