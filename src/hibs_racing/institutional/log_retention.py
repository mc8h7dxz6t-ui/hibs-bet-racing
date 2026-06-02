"""Tiered log retention — detailed 30d, brief 120d.

Only touches institutional audit tables (ledger_events, run_manifests) and
cron log files under logs/. Never modifies scoring, snapshots, or paper_bets.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from hibs_racing.config import ROOT, db_path, load_config
from hibs_racing.features.store import connect, init_db

_LOG_SECTION_RE = re.compile(r"^=== (\d{4}-\d{2}-\d{2}T[\d:]+Z) (.+?) ===\s*$", re.M)
_BRIEF_MARKER = "_log_tier"
_PROTECTED_TABLES = frozenset(
    {
        "paper_bets",
        "card_scores",
        "upcoming_runners",
        "scored_runner_snapshots",
        "ranker_features",
        "race_outcomes",
    }
)


@dataclass
class LogRetentionReport:
    detailed_days: int
    brief_days: int
    ledger_compacted: int = 0
    ledger_deleted: int = 0
    manifests_compacted: int = 0
    manifests_deleted: int = 0
    file_sections_briefed: int = 0
    file_brief_lines_pruned: int = 0
    dry_run: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "detailed_days": self.detailed_days,
            "brief_days": self.brief_days,
            "dry_run": self.dry_run,
            "ledger_compacted": self.ledger_compacted,
            "ledger_deleted": self.ledger_deleted,
            "manifests_compacted": self.manifests_compacted,
            "manifests_deleted": self.manifests_deleted,
            "file_sections_briefed": self.file_sections_briefed,
            "file_brief_lines_pruned": self.file_brief_lines_pruned,
            "notes": self.notes,
        }


def retention_config(cfg: dict | None = None) -> tuple[int, int]:
    cfg = cfg or load_config()
    block = cfg.get("logging", {}).get("retention", {})
    detailed = int(block.get("detailed_days", 30))
    brief = int(block.get("brief_days", 120))
    if brief < detailed:
        brief = detailed
    return detailed, brief


def _parse_created_at(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def brief_ledger_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Strip verbose fields; keep audit-relevant identifiers."""
    brief: dict[str, Any] = {_BRIEF_MARKER: "brief", "event_type": event_type}
    for key in (
        "bet_id",
        "runner_id",
        "race_id",
        "card_date",
        "manifest_id",
        "run_kind",
        "odds_source",
        "runner_count",
        "value_flag_count",
        "stake_units",
        "offered_win",
        "bet_type",
        "venue",
        "strategy_id",
        "pruned_count",
        "expected",
        "ledger",
    ):
        if key in payload and payload[key] is not None:
            brief[key] = payload[key]
    if event_type == "manifest_written" and "manifest_id" not in brief:
        brief["manifest_id"] = payload.get("manifest_id")
    return brief


def brief_manifest_extras(manifest_row: tuple) -> str:
    """Compact run_manifests.extras_json after detailed window."""
    card_date = manifest_row[3]
    odds_source = manifest_row[8]
    runner_count = manifest_row[9]
    value_flag_count = manifest_row[10]
    payload = {
        _BRIEF_MARKER: "brief",
        "card_date": card_date,
        "odds_source": odds_source,
        "runner_count": int(runner_count or 0),
        "value_flag_count": int(value_flag_count or 0),
    }
    return json.dumps(payload, sort_keys=True)


def _is_brief_payload(raw: str | None) -> bool:
    if not raw:
        return False
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, dict) and parsed.get(_BRIEF_MARKER) == "brief"


def run_db_log_retention(
    *,
    database: Path | None = None,
    detailed_days: int = 30,
    brief_days: int = 120,
    dry_run: bool = False,
) -> LogRetentionReport:
    report = LogRetentionReport(detailed_days=detailed_days, brief_days=brief_days, dry_run=dry_run)
    db = database or db_path(load_config())
    init_db(db)
    now = datetime.now(timezone.utc)
    detailed_cutoff = now - timedelta(days=detailed_days)
    brief_cutoff = now - timedelta(days=brief_days)

    with connect(db) as conn:
        ledger_rows = conn.execute(
            """
            SELECT event_id, event_type, payload_json, created_at
            FROM ledger_events
            ORDER BY created_at ASC
            """
        ).fetchall()

        for event_id, event_type, payload_json, created_at in ledger_rows:
            created = _parse_created_at(str(created_at))
            if created is None:
                continue
            if created >= detailed_cutoff:
                continue
            if created < brief_cutoff:
                report.ledger_deleted += 1
                if not dry_run:
                    conn.execute("DELETE FROM ledger_events WHERE event_id = ?", (event_id,))
                continue
            if _is_brief_payload(payload_json):
                continue
            try:
                payload = json.loads(payload_json) if payload_json else {}
            except json.JSONDecodeError:
                payload = {"raw_truncated": True}
            if not isinstance(payload, dict):
                payload = {"raw_truncated": True}
            brief = brief_ledger_payload(str(event_type), payload)
            report.ledger_compacted += 1
            if not dry_run:
                conn.execute(
                    "UPDATE ledger_events SET payload_json = ? WHERE event_id = ?",
                    (json.dumps(brief, sort_keys=True, default=str), event_id),
                )

        manifest_rows = conn.execute(
            """
            SELECT manifest_id, manifest_hash, run_kind, card_date, config_hash,
                   model_version, scoring_method, git_sha, odds_source,
                   runner_count, value_flag_count, extras_json, created_at
            FROM run_manifests
            ORDER BY created_at ASC
            """
        ).fetchall()

        for row in manifest_rows:
            created = _parse_created_at(str(row[12]))
            if created is None:
                continue
            if created >= detailed_cutoff:
                continue
            if created < brief_cutoff:
                report.manifests_deleted += 1
                if not dry_run:
                    conn.execute("DELETE FROM run_manifests WHERE manifest_id = ?", (row[0],))
                continue
            extras_raw = row[11]
            if extras_raw:
                try:
                    parsed = json.loads(extras_raw)
                    if isinstance(parsed, dict) and parsed.get(_BRIEF_MARKER) == "brief":
                        continue
                except json.JSONDecodeError:
                    pass
            report.manifests_compacted += 1
            if not dry_run:
                conn.execute(
                    "UPDATE run_manifests SET extras_json = ? WHERE manifest_id = ?",
                    (brief_manifest_extras(row), row[0]),
                )

        if not dry_run:
            conn.commit()

    report.notes.append(
        "DB retention limited to ledger_events + run_manifests; "
        f"protected: {', '.join(sorted(_PROTECTED_TABLES))}"
    )
    return report


def _brief_log_line(section_ts: str, section_name: str, body: str) -> str:
    status = "FAILED" if "FAILED (" in body else "OK"
    summary = ""
    json_line = ""
    for line in body.strip().splitlines():
        text = line.strip()
        if not text or text.startswith("==="):
            continue
        if text.startswith("{") or (text.startswith('"') and ":" in text):
            json_line = text[:240]
    if json_line:
        summary = json_line
    else:
        for line in reversed(body.strip().splitlines()):
            text = line.strip()
            if not text or text.startswith("==="):
                continue
            if text.startswith("OK:") or text.startswith("FAILED"):
                summary = text[:240]
                break
    if not summary:
        tail = [ln.strip() for ln in body.strip().splitlines() if ln.strip()][-3:]
        summary = " | ".join(tail)[:240]
    return f"{section_ts} {section_name} {status} {summary}"


def _split_log_sections(text: str) -> list[tuple[str, str, str]]:
    matches = list(_LOG_SECTION_RE.finditer(text))
    if not matches:
        return []
    sections: list[tuple[str, str, str]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections.append((match.group(1), match.group(2), text[start:end]))
    return sections


def run_file_log_retention(
    *,
    log_dir: Path | None = None,
    detailed_days: int = 30,
    brief_days: int = 120,
    dry_run: bool = False,
) -> LogRetentionReport:
    report = LogRetentionReport(detailed_days=detailed_days, brief_days=brief_days, dry_run=dry_run)
    root = log_dir or (ROOT / "logs")
    if not root.exists():
        report.notes.append(f"log dir missing: {root}")
        return report

    brief_dir = root / "brief"
    now = datetime.now(timezone.utc)
    detailed_cutoff = now - timedelta(days=detailed_days)
    brief_cutoff = now - timedelta(days=brief_days)

    for log_path in sorted(root.glob("*.log")):
        if log_path.name.startswith("."):
            continue
        raw = log_path.read_text(encoding="utf-8", errors="replace")
        sections = _split_log_sections(raw)
        if not sections:
            continue

        keep_blocks: list[str] = []
        brief_lines: list[str] = []
        briefed_this_file = 0
        for ts_s, name, block in sections:
            ts = _parse_created_at(ts_s)
            if ts is None or ts >= detailed_cutoff:
                keep_blocks.append(block.rstrip() + "\n")
                continue
            brief_lines.append(_brief_log_line(ts_s, name, block))
            briefed_this_file += 1
            report.file_sections_briefed += 1

        if brief_lines and not dry_run:
            brief_dir.mkdir(parents=True, exist_ok=True)
            brief_path = brief_dir / log_path.name
            existing = brief_path.read_text(encoding="utf-8", errors="replace") if brief_path.exists() else ""
            merged = (existing.rstrip() + "\n" if existing.strip() else "") + "\n".join(brief_lines) + "\n"
            brief_path.write_text(merged, encoding="utf-8")

        if briefed_this_file and not dry_run:
            log_path.write_text("".join(keep_blocks) if keep_blocks else "", encoding="utf-8")

    if brief_dir.exists() and not dry_run:
        for brief_path in brief_dir.glob("*.log"):
            lines = brief_path.read_text(encoding="utf-8", errors="replace").splitlines()
            kept: list[str] = []
            for line in lines:
                if not line.strip():
                    continue
                ts_s = line[:20]
                ts = _parse_created_at(ts_s)
                if ts is not None and ts < brief_cutoff:
                    report.file_brief_lines_pruned += 1
                    continue
                kept.append(line)
            brief_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")

    report.notes.append(f"file logs under {root}; brief archive under {brief_dir}")
    return report


def run_log_retention(
    *,
    database: Path | None = None,
    log_dir: Path | None = None,
    detailed_days: int | None = None,
    brief_days: int | None = None,
    dry_run: bool = False,
    files: bool = True,
    database_audit: bool = True,
) -> LogRetentionReport:
    cfg = load_config()
    d_default, b_default = retention_config(cfg)
    d_days = int(detailed_days if detailed_days is not None else d_default)
    b_days = int(brief_days if brief_days is not None else b_default)

    report = LogRetentionReport(detailed_days=d_days, brief_days=b_days, dry_run=dry_run)
    if database_audit:
        db_report = run_db_log_retention(
            database=database,
            detailed_days=d_days,
            brief_days=b_days,
            dry_run=dry_run,
        )
        report.ledger_compacted = db_report.ledger_compacted
        report.ledger_deleted = db_report.ledger_deleted
        report.manifests_compacted = db_report.manifests_compacted
        report.manifests_deleted = db_report.manifests_deleted
        report.notes.extend(db_report.notes)

    if files:
        file_report = run_file_log_retention(
            log_dir=log_dir,
            detailed_days=d_days,
            brief_days=b_days,
            dry_run=dry_run,
        )
        report.file_sections_briefed = file_report.file_sections_briefed
        report.file_brief_lines_pruned = file_report.file_brief_lines_pruned
        report.notes.extend(file_report.notes)

    return report
