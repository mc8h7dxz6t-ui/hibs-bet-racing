from __future__ import annotations

from pathlib import Path
from typing import Any

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect
from hibs_racing.tips.email_load import LoadedEmail, load_pasted_text, load_raw_input
from hibs_racing.tips.match import match_tip_to_runners
from hibs_racing.tips.parse_body import parse_tips_from_text
from hibs_racing.tips.settle import settle_matched_tips
from hibs_racing.tips.store import ensure_tipster_schema, insert_tip, tipster_summary, update_tip_match


def _collect_paths(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        files: list[Path] = []
        for pattern in ("*.eml", "*.txt", "*.text", "*.html"):
            files.extend(sorted(path.glob(pattern)))
        return files
    return []


def ingest_email_file(
    path: Path,
    *,
    database: Path | None = None,
    default_date: str | None = None,
    match: bool = True,
    settle: bool = False,
    store_body: bool = True,
) -> dict[str, Any]:
    db = database or db_path(load_config())
    ensure_tipster_schema(db)

    loaded = load_raw_input(path, default_date=default_date)
    return ingest_loaded_email(
        loaded,
        database=db,
        match=match,
        settle=settle,
        store_body=store_body,
    )


def ingest_loaded_email(
    loaded: LoadedEmail,
    *,
    database: Path | None = None,
    match: bool = True,
    settle: bool = False,
    store_body: bool = True,
) -> dict[str, Any]:
    db = database or db_path(load_config())
    ensure_tipster_schema(db)

    card_date = loaded.card_date
    tips = parse_tips_from_text(loaded.body_text, default_card_date=card_date)
    stats: dict[str, Any] = {
        "file": loaded.path,
        "subject": loaded.subject,
        "received_at": loaded.received_at,
        "card_date": card_date,
        "tips_found": len(tips),
        "inserted": 0,
        "skipped_duplicate": 0,
        "matched": 0,
        "unmatched": 0,
        "tips": [],
    }

    body_store = loaded.body_text[:20000] if store_body else None

    with connect(db) as conn:
        for tip in tips:
            tip_id, inserted = insert_tip(
                conn,
                email_message_id=loaded.message_id,
                source_file=loaded.path,
                source_kind=loaded.source_kind,
                received_at=loaded.received_at,
                subject=loaded.subject,
                card_date=tip.card_date or card_date,
                horse_name=tip.horse_name,
                course=tip.course,
                off_time=tip.off_time,
                odds_quoted=tip.odds_quoted,
                odds_decimal=tip.odds_decimal,
                bet_type=tip.bet_type,
                stable_intel=tip.stable_intel,
                confidence=tip.confidence,
                raw_excerpt=tip.raw_excerpt,
                tipster_review=tip.review_text,
                raw_email_body=body_store,
            )
            if not inserted:
                stats["skipped_duplicate"] += 1
                continue
            stats["inserted"] += 1

            match_status = "unmatched"
            runner_id = race_id = None
            if match:
                runner_id, race_id, match_status = match_tip_to_runners(
                    conn,
                    card_date=tip.card_date or card_date,
                    horse_name=tip.horse_name,
                    course=tip.course,
                    off_time=tip.off_time,
                )
                update_tip_match(conn, tip_id, runner_id=runner_id, race_id=race_id, match_status=match_status)
                if match_status == "matched":
                    stats["matched"] += 1
                else:
                    stats["unmatched"] += 1

            stats["tips"].append(
                {
                    "tip_id": tip_id,
                    "horse_name": tip.horse_name,
                    "course": tip.course,
                    "off_time": tip.off_time,
                    "odds_quoted": tip.odds_quoted,
                    "stable_intel": tip.stable_intel,
                    "match_status": match_status,
                    "runner_id": runner_id,
                }
            )

        if settle:
            stats["settled"] = settle_matched_tips(conn)
        conn.commit()

    stats["summary"] = tipster_summary(db)
    return stats


def _merge_ingest_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    combined: dict[str, Any] = {
        "chunks": len(results),
        "inserted": 0,
        "skipped_duplicate": 0,
        "tips_found": 0,
        "matched": 0,
        "unmatched": 0,
        "results": results,
    }
    for r in results:
        combined["inserted"] += r.get("inserted", 0)
        combined["skipped_duplicate"] += r.get("skipped_duplicate", 0)
        combined["tips_found"] += r.get("tips_found", 0)
        combined["matched"] += r.get("matched", 0)
        combined["unmatched"] += r.get("unmatched", 0)
    return combined


def ingest_pasted_text(
    text: str,
    *,
    database: Path | None = None,
    default_date: str | None = None,
    match: bool = True,
    settle: bool = False,
) -> dict[str, Any]:
    """Ingest from copy-paste (body-only, full headers, or multiple emails separated by ---)."""
    db = database or db_path(load_config())
    ensure_tipster_schema(db)
    chunks = load_pasted_text(text, default_date=default_date)
    results = [
        ingest_loaded_email(
            loaded,
            database=db,
            match=match,
            settle=False,
            store_body=True,
        )
        for loaded in chunks
    ]
    combined = _merge_ingest_results(results)
    if settle and chunks:
        with connect(db) as conn:
            combined["settled"] = settle_matched_tips(conn)
            conn.commit()
    combined["summary"] = tipster_summary(db)
    return combined


def ingest_from_imap(
    *,
    database: Path | None = None,
    match: bool = True,
    settle: bool = False,
    unseen_only: bool | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    from hibs_racing.tips.imap_fetch import fetch_imap_messages

    db = database or db_path(load_config())
    ensure_tipster_schema(db)
    messages = fetch_imap_messages(unseen_only=unseen_only, limit=limit)
    results = [
        ingest_loaded_email(loaded, database=db, match=match, settle=False, store_body=True)
        for loaded in messages
    ]
    combined = _merge_ingest_results(results)
    combined["emails_fetched"] = len(messages)
    if settle and messages:
        with connect(db) as conn:
            combined["settled"] = settle_matched_tips(conn)
            conn.commit()
    combined["summary"] = tipster_summary(db)
    return combined


def ingest_tip_paths(
    paths: list[Path],
    *,
    database: Path | None = None,
    default_date: str | None = None,
    match: bool = True,
    settle: bool = False,
) -> dict[str, Any]:
    db = database or db_path(load_config())
    combined: dict[str, Any] = {
        "files": len(paths),
        "inserted": 0,
        "skipped_duplicate": 0,
        "tips_found": 0,
        "results": [],
    }
    for path in paths:
        result = ingest_email_file(
            path,
            database=db,
            default_date=default_date,
            match=match,
            settle=False,
            store_body=True,
        )
        combined["inserted"] += result["inserted"]
        combined["skipped_duplicate"] += result["skipped_duplicate"]
        combined["tips_found"] += result["tips_found"]
        combined["results"].append(result)

    if settle and paths:
        ensure_tipster_schema(db)
        with connect(db) as conn:
            combined["settled"] = settle_matched_tips(conn)
            conn.commit()
        combined["summary"] = tipster_summary(db)
    elif paths:
        combined["summary"] = tipster_summary(db)
    return combined
