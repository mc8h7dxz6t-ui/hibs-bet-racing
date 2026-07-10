"""No-illusion truth plane — every evidence surface must carry this."""

from __future__ import annotations

from typing import Any

from hibs_predictor.stack_truth import (
    BUNDLE_LABELS_ONLY,
    FABRICATED_PRODUCT_NAMES,
    stack_truth_summary,
)


def honesty_disclaimer() -> dict[str, Any]:
    """Plain-language facts — attach to gates, health, and verify scripts."""
    st = stack_truth_summary()
    return {
        "what_this_is": (
            "Sports betting research infrastructure: football prediction audit + CLV logging, "
            "horse racing cards and paper ledger, optional shadow trading soak."
        ),
        "what_this_is_not": [
            "Enterprise fintech, insurtech, or cybersecurity platform",
            "SOC2 Type II / ISO 27001 certified service",
            "Proven profitable automated betting product",
            "Four isolated PostgreSQL HA cluster (uses SQLite on VPS)",
        ],
        "fabricated_external_names": list(FABRICATED_PRODUCT_NAMES),
        "bundle_labels_only_not_products": list(BUNDLE_LABELS_ONLY),
        "buyer_ready_means": (
            "Internal gate checklist passed (engineering + forward evidence). "
            "Does NOT mean external buyer, PE diligence pass, or revenue-ready product."
        ),
        "commercial_tier_means": (
            "Internal ops shorthand only (pilot / design-partner / license-candidate). "
            "Not a SKU price, not a VC valuation, not a substitute for settled-edge proof."
        ),
        "evidence_grade_means": "Ops quality letter grade from gate pass ratio — not model alpha proof.",
        "stack_truth": st,
    }


def attach_honesty(payload: dict[str, Any]) -> dict[str, Any]:
    """Merge honesty block without mutating caller's other keys."""
    out = dict(payload)
    out["honesty"] = honesty_disclaimer()
    out["illusion_safe"] = False  # explicit: mislabeling this stack is unsafe for external sale
    return out


def evidence_complete_label(buyer_ready: bool) -> str:
    """Human label for scripts — avoids 'buyer' in external-facing text."""
    return "evidence_gates_complete" if buyer_ready else "evidence_gates_incomplete"
