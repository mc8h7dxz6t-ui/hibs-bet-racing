"""Paper ledger reconciliation — derived picks vs recorded bets (trading_core pattern)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hibs_racing.backtest.gate_benchmark import _apply_gate_flags
from hibs_racing.backtest.snapshot_store import load_snapshots_for_card, scoring_config_hash
from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.institutional.contracts import PaperReconciliationResult, ReconDiscrepancy
from hibs_racing.institutional.run_manifest import latest_manifest_for_date


def _expected_value_runners_from_snapshots(
    db: Path,
    card_date: str,
    paper_cfg: dict,
) -> set[str]:
    cfg_hash = scoring_config_hash(paper_cfg)
    snap = load_snapshots_for_card(db, card_date, config_hash=cfg_hash)
    if snap.empty:
        return set()
    g1 = _apply_gate_flags(snap, paper_cfg)
    return set(g1.loc[g1["flag_gate1"] == 1, "runner_id"].astype(str).tolist())


def _ledger_value_runners(db: Path, card_date: str) -> set[str]:
    init_db(db)
    with connect(db) as conn:
        rows = conn.execute(
            """
            SELECT pb.runner_id
            FROM paper_bets pb
            JOIN upcoming_runners ur ON ur.runner_id = pb.runner_id
            WHERE ur.card_date = ?
              AND pb.is_value_pick = 1
              AND pb.backtest = 0
            """,
            (card_date,),
        ).fetchall()
    if rows:
        return {str(r[0]) for r in rows}
    # Fallback: bets created on card_date via created_at prefix
    with connect(db) as conn:
        rows = conn.execute(
            """
            SELECT runner_id FROM paper_bets
            WHERE is_value_pick = 1 AND backtest = 0
              AND created_at LIKE ?
            """,
            (f"{card_date}%",),
        ).fetchall()
    return {str(r[0]) for r in rows}


def _delete_live_value_picks(db: Path, card_date: str, runner_ids: list[str]) -> int:
    if not runner_ids:
        return 0
    deleted = 0
    with connect(db) as conn:
        for rid in runner_ids:
            cur = conn.execute(
                """
                DELETE FROM paper_bets
                WHERE runner_id = ?
                  AND backtest = 0
                  AND is_value_pick = 1
                  AND runner_id IN (
                    SELECT runner_id FROM upcoming_runners WHERE card_date = ?
                  )
                """,
                (rid, card_date),
            )
            deleted += int(cur.rowcount)
        conn.commit()
    return deleted


def sync_paper_ledger_to_scored(
    scored: pd.DataFrame,
    *,
    card_date: str,
    database: Path | None = None,
    stake: float = 1.0,
    manifest_id: str | None = None,
) -> PaperReconciliationResult:
    """
    Align live paper_bets with current scored value_flag rows for one card date.
    Prunes stale extras, then logs any missing picks (deduped).
    """
    from hibs_racing.cards.score_card import paper_log_value_picks
    from hibs_racing.institutional.ledger_events import append_ledger_event

    db = database or db_path(load_config())
    before = reconcile_paper_ledger_from_scores(scored, card_date=card_date, database=db)
    if before.extra_in_ledger:
        removed = _delete_live_value_picks(db, card_date, before.extra_in_ledger)
        append_ledger_event(
            event_type="ledger_pruned",
            manifest_id=manifest_id,
            payload={"card_date": card_date, "removed": removed, "runner_ids": before.extra_in_ledger[:50]},
            database=db,
        )
    value = scored[scored.get("value_flag", 0) == 1] if not scored.empty else scored
    if not value.empty:
        paper_log_value_picks(value, stake=stake)
    return reconcile_paper_ledger_from_scores(scored, card_date=card_date, database=db)


def _load_live_scored_card(db: Path, card_date: str) -> pd.DataFrame:
    init_db(db)
    with connect(db) as conn:
        return pd.read_sql_query(
            """
            SELECT u.*, c.value_flag, c.value_gate_reason, c.scoring_method
            FROM upcoming_runners u
            INNER JOIN card_scores c ON c.runner_id = u.runner_id
            WHERE u.card_date = ?
            """,
            conn,
            params=(card_date,),
        )


def reconcile_paper_ledger(
    card_date: str,
    *,
    database: Path | None = None,
) -> PaperReconciliationResult:
    """
    Independent truth check: live card_scores vs paper_bets when card is in DB,
    else snapshot-derived Gate1 picks for historical dates.
    """
    cfg = load_config()
    db = database or db_path(cfg)
    live = _load_live_scored_card(db, card_date)
    if not live.empty:
        return reconcile_paper_ledger_from_scores(live, card_date=card_date, database=db)

    paper_cfg = cfg.get("paper", {})
    manifest = latest_manifest_for_date(card_date, database=db)

    expected = _expected_value_runners_from_snapshots(db, card_date, paper_cfg)
    ledger = _ledger_value_runners(db, card_date)

    missing = sorted(expected - ledger)
    extra = sorted(ledger - expected)
    mismatches: list[ReconDiscrepancy] = []

    if missing:
        for rid in missing[:50]:
            mismatches.append(
                ReconDiscrepancy(
                    status="MISSING_IN_LEDGER",
                    field="value_pick",
                    runner_id=rid,
                    internal_value="expected",
                    derived_value="absent",
                )
            )
    if extra:
        for rid in extra[:50]:
            mismatches.append(
                ReconDiscrepancy(
                    status="EXTRA_IN_LEDGER",
                    field="value_pick",
                    runner_id=rid,
                    internal_value="absent",
                    derived_value="recorded",
                )
            )

    is_clean = not missing and not extra
    return PaperReconciliationResult(
        is_clean=is_clean,
        manifest_id=manifest.manifest_id if manifest else None,
        card_date=card_date,
        expected_value_picks=len(expected),
        ledger_value_picks=len(ledger),
        missing_in_ledger=missing,
        extra_in_ledger=extra,
        field_mismatches=mismatches,
        discrepancies=mismatches,
    )


def reconcile_paper_ledger_from_scores(
    scored: pd.DataFrame,
    *,
    card_date: str,
    database: Path | None = None,
) -> PaperReconciliationResult:
    """Reconcile immediately after refresh using live scored frame (no snapshot required)."""
    cfg = load_config()
    db = database or db_path(cfg)
    paper_cfg = cfg.get("paper", {})
    manifest = latest_manifest_for_date(card_date, database=db)

    expected = set(scored.loc[scored["value_flag"] == 1, "runner_id"].astype(str).tolist())
    ledger = _ledger_value_runners(db, card_date)
    missing = sorted(expected - ledger)
    extra = sorted(ledger - expected)
    mismatches = [
        ReconDiscrepancy("MISSING_IN_LEDGER", "value_pick", rid, "expected", "absent") for rid in missing[:50]
    ] + [ReconDiscrepancy("EXTRA_IN_LEDGER", "value_pick", rid, "absent", "recorded") for rid in extra[:50]]
    return PaperReconciliationResult(
        is_clean=not missing and not extra,
        manifest_id=manifest.manifest_id if manifest else None,
        card_date=card_date,
        expected_value_picks=len(expected),
        ledger_value_picks=len(ledger),
        missing_in_ledger=missing,
        extra_in_ledger=extra,
        field_mismatches=mismatches,
        discrepancies=mismatches,
    )
