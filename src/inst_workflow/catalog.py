"""Proof Console catalog — all 11 institutional SKUs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProductCatalogEntry:
    id: str
    sku: str
    label: str
    tagline: str
    default_db: str
    bundle_name: str
    cli: str

    def db_path(self, demo_dir: Path | None = None) -> Path:
        base = demo_dir or Path(os.getenv("PORTFOLIO_DEMO_DIR", "data/demo/portfolio"))
        return base / self.default_db

    def export_tarball(self, export_dir: Path) -> Path:
        return export_dir / f"{self.bundle_name}.tar"

    def to_dict(self, *, demo_dir: Path | None = None) -> dict:
        db = self.db_path(demo_dir)
        return {
            "id": self.id,
            "sku": self.sku,
            "label": self.label,
            "tagline": self.tagline,
            "cli": self.cli,
            "database": str(db),
            "database_present": db.is_file(),
            "bundle_name": self.bundle_name,
        }


PRODUCT_CATALOG: tuple[ProductCatalogEntry, ...] = (
    ProductCatalogEntry(
        "compliance",
        "compliance-logger",
        "Compliance Logger",
        "Tamper-proof regulated decision audit",
        "compliance.sqlite",
        "compliance_bundle",
        "compliance-log",
    ),
    ProductCatalogEntry(
        "proxy",
        "proxy-risk",
        "Proxy-Risk",
        "Outbound API firewall + cryptographic audit",
        "proxy.sqlite",
        "proxy_bundle",
        "proxy-risk",
    ),
    ProductCatalogEntry(
        "altdata",
        "altdata",
        "Alt-Data",
        "Feed coverage SLA + poll proof",
        "altdata.sqlite",
        "altdata_bundle",
        "altdata",
    ),
    ProductCatalogEntry(
        "ai-kit",
        "ai-kit",
        "AI Kit",
        "Agent rate limits, checkpoints, trace audit",
        "ai_kit_trace.sqlite",
        "ai_kit_bundle",
        "ai-kit",
    ),
    ProductCatalogEntry(
        "webhook-mesh",
        "webhook-mesh",
        "Webhook Mesh",
        "Never double-process a billing webhook",
        "webhook_mesh.sqlite",
        "webhook_mesh_bundle",
        "webhook-mesh",
    ),
    ProductCatalogEntry(
        "ad-guard",
        "ad-guard",
        "Ad Guard",
        "Marketing API spend kill + gate audit",
        "ad_guard.sqlite",
        "ad_guard_bundle",
        "ad-guard",
    ),
    ProductCatalogEntry(
        "health",
        "health-telemetry",
        "Health Telemetry",
        "Device batch tamper evidence",
        "health.sqlite",
        "health_bundle",
        "health-telemetry",
    ),
    ProductCatalogEntry(
        "model-governor",
        "model-governor",
        "ModelGovernor",
        "ML lifecycle governance + deploy proof",
        "model_governor.sqlite",
        "model_governor_bundle",
        "model-governor",
    ),
    ProductCatalogEntry(
        "drift-gate",
        "drift-gate",
        "Drift Gate",
        "PSI/KS drift at the proxy",
        "drift_gate.sqlite",
        "drift_gate_bundle",
        "drift-gate",
    ),
    ProductCatalogEntry(
        "webhook-replay",
        "webhook-replay",
        "Webhook Replay",
        "Byte-identical webhook replay",
        "webhook_replay.sqlite",
        "webhook_replay_bundle",
        "webhook-replay",
    ),
    ProductCatalogEntry(
        "spend-guard",
        "spend-guard",
        "Spend Guard",
        "Reserve before LLM dispatch",
        "spend_guard.sqlite",
        "spend_guard_bundle",
        "spend-guard",
    ),
    ProductCatalogEntry(
        "agent-ledger",
        "agent-ledger",
        "Agent Ledger",
        "Permit agent tools before execution",
        "agent_ledger.sqlite",
        "agent_ledger_bundle",
        "agent-ledger",
    ),
)


def catalog_by_id(product_id: str) -> ProductCatalogEntry | None:
    key = (product_id or "").strip().lower()
    for entry in PRODUCT_CATALOG:
        if entry.id == key:
            return entry
    return None


def list_catalog(*, demo_dir: Path | None = None) -> list[dict]:
    return [e.to_dict(demo_dir=demo_dir) for e in PRODUCT_CATALOG]
