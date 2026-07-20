"""Neutral engine pick display — always surface top model output with gate context."""

from __future__ import annotations

import math
from typing import Any

from hibs_racing.cards.enrich_display import format_gate_reason
from hibs_racing.cards.ui_frame import gate_reason_is_clear, is_value_pick
from hibs_racing.config import load_config
from hibs_racing.pick_explain import attach_pick_explanations
from hibs_racing.web_format import fmt_prob_phrase, normalize_prob_pct


def _paper_cfg() -> dict[str, Any]:
    return load_config().get("paper", {}) or {}


def _pct(value: object) -> float:
    return normalize_prob_pct(value) or 0.0


def loose_min_data_quality_pct(paper_cfg: dict | None = None) -> int:
    cfg = paper_cfg or _paper_cfg()
    raw = cfg.get("display_loose_min_data_quality_pct")
    if raw is None:
        raw = cfg.get("loose_min_data_quality_pct")
    if raw is None:
        return 60
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 60


def loose_allowed_steam_gates(paper_cfg: dict | None = None) -> set[str]:
    cfg = paper_cfg or _paper_cfg()
    raw = cfg.get("display_loose_steam_gates") or cfg.get("loose_allowed_steam_gates")
    if isinstance(raw, (list, tuple)) and raw:
        return {str(g).strip().lower() for g in raw if str(g).strip()}
    return {"proceed", "scale_up", "scale_down", "unknown"}


def _strict_allowed_steam_gates(paper_cfg: dict) -> set[str]:
    raw = paper_cfg.get("allowed_steam_gates", ["proceed", "scale_up", "unknown"])
    if isinstance(raw, (list, tuple)):
        return {str(g).strip().lower() for g in raw if str(g).strip()}
    return {"proceed", "scale_up", "unknown"}


def passes_strict_pick(pick: dict[str, Any], *, paper_cfg: dict | None = None) -> bool:
    cfg = paper_cfg or _paper_cfg()
    min_dq = int(cfg.get("min_data_quality_pct") or 75)
    allowed = _strict_allowed_steam_gates(cfg)
    if not is_value_pick(pick.get("value_flag")):
        return False
    if not gate_reason_is_clear(pick.get("value_gate_reason")):
        return False
    if int(pick.get("data_quality_pct") or 0) < min_dq:
        return False
    if str(pick.get("steam_gate") or "proceed").lower() not in allowed:
        return False
    return True


def passes_loose_pick(pick: dict[str, Any], *, paper_cfg: dict | None = None) -> bool:
    cfg = paper_cfg or _paper_cfg()
    min_dq = loose_min_data_quality_pct(cfg)
    allowed = loose_allowed_steam_gates(cfg)
    steam = str(pick.get("steam_gate") or "proceed").lower()
    dq = int(pick.get("data_quality_pct") or 0)
    if dq < min_dq:
        return False
    if steam not in allowed:
        return False
    return True


def load_holdout_accuracy() -> dict[str, Any]:
    try:
        from hibs_racing.models.feature_impact import load_feature_impact_report

        report = load_feature_impact_report() or {}
        holdout = report.get("holdout") or {}
        if holdout.get("place_auc") is not None or holdout.get("top1_hit_rate") is not None:
            return holdout
    except Exception:
        pass
    return {}


def build_pick_accuracy(pick: dict[str, Any], *, holdout: dict[str, Any] | None = None) -> dict[str, Any]:
    """Quantified model readout for each pick — probabilities with holdout context."""
    place_p = _pct(pick.get("model_place_prob"))
    combo = _pct(pick.get("combo_bayes_place"))
    score_raw = pick.get("place_score")
    if score_raw is None or (isinstance(score_raw, float) and math.isnan(score_raw)):
        score = place_p * 0.65 + combo * 0.35
    else:
        score = _pct(score_raw)

    lines: list[str] = [
        (
            f"Blended place score {score:.0f}% "
            f"(model {fmt_prob_phrase(place_p)} · combo {fmt_prob_phrase(combo)})."
        )
    ]
    h = holdout or {}
    place_auc = h.get("place_auc")
    top1 = h.get("top1_hit_rate")
    if place_auc is not None:
        try:
            lines.append(f"Ranker holdout place AUC {float(place_auc):.2f} on out-of-sample cards.")
        except (TypeError, ValueError):
            pass
    if top1 is not None:
        try:
            lines.append(f"Top-ranked selection hit rate {float(top1):.1%} on holdout window.")
        except (TypeError, ValueError):
            pass

    rank = pick.get("day_rank") or pick.get("display_rank")
    if rank:
        lines.insert(0, f"Engine rank #{rank} place angle for today's card.")

    return {
        "place_prob_pct": round(place_p, 1),
        "combo_prob_pct": round(combo, 1),
        "place_score_pct": round(score, 1),
        "accuracy_lines": lines,
        "accuracy_summary": lines[0],
    }


def build_gate_notes(pick: dict[str, Any]) -> list[str]:
    """Operational context for the card — factual, not rejection language."""
    notes: list[str] = []
    place_pct = round(_pct(pick.get("model_place_prob")))
    if place_pct > 0:
        notes.append(f"Place {place_pct}%")
    dq = int(pick.get("data_quality_pct") or 0)
    if dq > 0:
        notes.append(f"Data {dq}%")
    if is_value_pick(pick.get("value_flag")):
        notes.append("Value signal")
    steam = str(pick.get("steam_gate") or "proceed").lower()
    if steam and steam != "unknown":
        notes.append(f"Steam {steam.replace('_', ' ')}")
    reason = pick.get("value_gate_reason")
    if not gate_reason_is_clear(reason):
        label = format_gate_reason(reason)
        if label:
            notes.append(label)
    ev = pick.get("ew_combined_ev")
    if ev is not None:
        try:
            notes.append(f"EV {float(ev):.2f}")
        except (TypeError, ValueError):
            pass
    return notes


def classify_display_pick(pick: dict[str, Any], *, paper_cfg: dict | None = None) -> dict[str, Any]:
    strict = passes_strict_pick(pick, paper_cfg=paper_cfg)
    loose = passes_loose_pick(pick, paper_cfg=paper_cfg)
    if strict:
        tier, label = "paper_ready", "Paper-ready"
    elif loose:
        tier, label = "watchlist", "Watchlist"
    else:
        tier, label = "engine_lead", "Engine lead"
    return {
        "display_tier": tier,
        "display_tier_label": label,
        "paper_ready": strict,
        "watchlist_ok": loose,
        "gate_notes": build_gate_notes(pick),
    }


def enrich_pick_display(pick: dict[str, Any], *, paper_cfg: dict | None = None, holdout: dict | None = None) -> dict[str, Any]:
    out = {**pick}
    out.update(classify_display_pick(out, paper_cfg=paper_cfg))
    out["pick_accuracy"] = build_pick_accuracy(out, holdout=holdout)
    reasons = list(out.get("pick_reasons") or [])
    for line in out["pick_accuracy"].get("accuracy_lines") or []:
        if line not in reasons:
            reasons.append(line)
    if reasons:
        out["pick_reasons"] = reasons[:5]
        out.setdefault("pick_summary", reasons[0])
    return out


def build_engine_display_picks(
    meetings: list[dict],
    frame,
    *,
    top_n: int = 6,
) -> list[dict[str, Any]]:
    """Top model place angles — always returned when cards exist."""
    from hibs_racing.monitor import top_places_of_day
    from hibs_racing.utils.monetization import attach_monetized_links
    from hibs_racing.web_service import attach_deep_links_to_picks, novice_pick_candidates

    if frame is None or getattr(frame, "empty", True):
        return []

    cfg = _paper_cfg()
    holdout = load_holdout_accuracy()
    limit = int(cfg.get("display_top_n") or top_n)
    picks = top_places_of_day(frame, top_n=limit)
    if not picks:
        return []

    picks = attach_pick_explanations(picks, frame)
    picks = attach_deep_links_to_picks(picks, meetings)
    picks = attach_monetized_links(picks)
    by_runner = {str(c.get("runner_id") or ""): c for c in novice_pick_candidates(meetings)}

    out: list[dict[str, Any]] = []
    for rank, pick in enumerate(picks, start=1):
        rid = str(pick.get("runner_id") or "")
        merged = {**(by_runner.get(rid) or {}), **pick}
        merged["display_rank"] = rank
        out.append(enrich_pick_display(merged, paper_cfg=cfg, holdout=holdout))
    return out


def format_engine_digest_lines(picks: list[dict[str, Any]], *, limit: int = 3) -> list[str]:
    lines: list[str] = []
    for pick in picks[:limit]:
        rank = pick.get("display_rank") or len(lines) + 1
        horse = pick.get("horse_name") or "?"
        course = pick.get("course") or "?"
        off = pick.get("off_time") or "?"
        tier = pick.get("display_tier_label") or "Engine lead"
        acc = (pick.get("pick_accuracy") or {}).get("accuracy_summary")
        summary = pick.get("pick_summary") or acc
        lines.append(f"#{rank} {horse} ({off} {course}) · {tier}")
        if summary:
            lines.append(f"   {summary}")
        for reason in (pick.get("pick_reasons") or [])[1:3]:
            lines.append(f"   — {reason}")
        lines.append("")
    return lines
