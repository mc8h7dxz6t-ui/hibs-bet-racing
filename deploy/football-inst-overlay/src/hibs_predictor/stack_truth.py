"""Honest stack map — sports research infrastructure, not rebranded enterprise vaporware."""

from __future__ import annotations

from typing import Any

# Names that appear in external "enterprise platform" decks but do NOT exist in this repo.
FABRICATED_PRODUCT_NAMES: tuple[str, ...] = (
    "CyberGovernor",
    "AlgoFreeze",
    "ClaimGate",
    "Crystal Commit Protocol",
    "ZkClaimAudit",
    "Mesh Cybersecurity",
)

# FinanceGovernor is a sales bundle label only (Spend Guard + Drift Gate), not a runnable service.
BUNDLE_LABELS_ONLY: tuple[str, ...] = (
    "FinanceGovernor",
    "Insurance Governor",
)

STACK_SERVICES: tuple[dict[str, Any], ...] = (
    {
        "id": "football",
        "label": "Football predictions + CLV audit",
        "port": 8000,
        "code": "hibs-bet (overlay in deploy/football-inst-overlay/)",
        "database": "SQLite prediction_audit.sqlite",
        "domain": "sports_betting_research",
    },
    {
        "id": "racing",
        "label": "Horse racing cards + paper ledger",
        "port": 5003,
        "code": "src/hibs_racing/",
        "database": "SQLite feature_store.sqlite (+ optional inst_spine.sqlite)",
        "domain": "sports_betting_research",
    },
    {
        "id": "fve",
        "label": "Line shopper / exchange lines proxy",
        "port": 8010,
        "code": "external football-app Docker (not in this repo)",
        "database": "host-specific",
        "domain": "sports_betting_research",
    },
    {
        "id": "trading_shadow",
        "label": "Trading shadow soak (frozen)",
        "port": 9108,
        "code": "deploy/football-inst-overlay/.../trading_core/",
        "database": "n/a",
        "domain": "experimental_rd",
    },
    {
        "id": "inst_pp",
        "label": "Inst++ audit CLI portfolio (12 SKUs)",
        "port": 8790,
        "code": "src/inst_workflow/, src/compliance_log/, src/model_governor/, …",
        "database": "SQLite per SKU; optional Postgres DSN for compliance/spend",
        "domain": "governance_tooling_separate_from_sports_runtime",
    },
)


def stack_truth_summary() -> dict[str, Any]:
    """Surface for /api/health — diligence auditors see real names and storage."""
    return {
        "posture": "sports_betting_research_stack",
        "enterprise_certifications": [],
        "note": (
            "This repository is primarily a horse-racing research engine and football "
            "audit overlay. Inst++ SKUs are separate CLI governance tools on a shared spine — "
            "not SOC2-certified fintech infrastructure. External decks that map these ports "
            "to CyberGovernor/AlgoFreeze/ClaimGate are not supported by this codebase."
        ),
        "services": list(STACK_SERVICES),
        "fabricated_names_not_in_repo": list(FABRICATED_PRODUCT_NAMES),
        "bundle_labels_only": list(BUNDLE_LABELS_ONLY),
        "execution_policy": {
            "racing_live_betting": "EXECUTION_DISABLED=True (hardcoded)",
            "football_stakes": "evidence-gated; buyer_ready required before scale",
        },
        "database_reality": {
            "primary": "SQLite on VPS block storage",
            "postgres": "optional design-partner profile for Inst++ compliance/spend ledgers only",
            "four_isolated_postgres_claim": False,
        },
    }
