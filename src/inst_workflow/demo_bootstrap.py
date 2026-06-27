"""Run per-SKU demo scripts to seed Proof Console databases."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from inst_workflow.catalog import PRODUCT_CATALOG, ProductCatalogEntry

ROOT = Path(__file__).resolve().parents[2]


def _demo_script_args(entry: ProductCatalogEntry, demo_dir: Path) -> list[str]:
    """Build argv for scripts/demo_<product>.sh matching demo_portfolio_all.sh."""
    d = demo_dir
    mapping: dict[str, list[str]] = {
        "compliance": [
            str(d / "compliance.sqlite"),
            str(d / "compliance_bundle"),
            str(d / "compliance_bundle.tar"),
        ],
        "proxy": [
            str(d / "proxy.sqlite"),
            str(d / "proxy_bundle"),
            str(d / "proxy_bundle.tar"),
        ],
        "altdata": [str(d / "altdata.sqlite"), str(d / "altdata_bundle.tar")],
        "ai-kit": [str(d / "ai_kit_trace.sqlite"), str(d / "ai_kit_bundle.tar")],
        "webhook-mesh": [
            str(d / "webhook_mesh.sqlite"),
            str(d / "webhook_mesh_bundle.tar"),
        ],
        "ad-guard": [str(d / "ad_guard.sqlite"), str(d / "ad_guard_bundle.tar")],
        "health": [str(d / "health.sqlite"), str(d / "health_bundle.tar")],
        "model-governor": [
            str(d / "model_governor.sqlite"),
            str(d / "model_governor_bundle.tar"),
        ],
        "drift-gate": [
            str(d / "drift_baseline.json"),
            str(d / "drift_gate.sqlite"),
            str(d / "drift_gate_bundle.tar"),
        ],
        "webhook-replay": [
            str(d / "captures"),
            str(d / "webhook_replay.sqlite"),
            str(d / "webhook_replay_bundle.tar"),
        ],
        "spend-guard": [
            str(d / "spend_wallet.sqlite"),
            str(d / "spend_guard.sqlite"),
            str(d / "spend_guard_bundle.tar"),
        ],
        "agent-ledger": [
            str(d / "agent_ledger.sqlite"),
            str(d / "agent_ledger_permits.sqlite"),
            str(d / "agent_ledger_bundle.tar"),
        ],
    }
    args = mapping.get(entry.id)
    if args is None:
        raise ValueError(f"no demo bootstrap mapping for {entry.id}")
    return args


def demo_script_path(entry: ProductCatalogEntry) -> Path:
    scripts = {
        "compliance": "demo_compliance_logger.sh",
        "proxy": "demo_proxy_risk.sh",
        "altdata": "demo_altdata.sh",
        "ai-kit": "demo_ai_kit.sh",
        "webhook-mesh": "demo_webhook_mesh.sh",
        "ad-guard": "demo_ad_guard.sh",
        "health": "demo_health_telemetry.sh",
        "model-governor": "demo_model_governor.sh",
        "drift-gate": "demo_drift_gate.sh",
        "webhook-replay": "demo_webhook_replay.sh",
        "spend-guard": "demo_spend_guard.sh",
        "agent-ledger": "demo_agent_ledger.sh",
    }
    name = scripts.get(entry.id)
    if not name:
        raise ValueError(f"no demo script for {entry.id}")
    return ROOT / "scripts" / name


def bootstrap_product(
    entry: ProductCatalogEntry,
    *,
    demo_dir: Path,
    skip_live: bool = True,
) -> dict:
    script = demo_script_path(entry)
    if not script.is_file():
        raise FileNotFoundError(f"demo script missing: {script}")
    demo_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["SKIP_LIVE"] = "1" if skip_live else "0"
    env["PORTFOLIO_DEMO_DIR"] = str(demo_dir)
    cmd = [str(script), *_demo_script_args(entry, demo_dir)]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    db = entry.db_path(demo_dir)
    ok = proc.returncode == 0 and db.is_file()
    return {
        "ok": ok,
        "product_id": entry.id,
        "sku": entry.sku,
        "script": str(script),
        "database": str(db),
        "database_present": db.is_file(),
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


def bootstrap_all(*, demo_dir: Path, skip_live: bool = True) -> list[dict]:
    return [
        bootstrap_product(entry, demo_dir=demo_dir, skip_live=skip_live)
        for entry in PRODUCT_CATALOG
    ]
