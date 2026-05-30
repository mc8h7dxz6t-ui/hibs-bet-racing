#!/usr/bin/env python3
"""Diagnostic: LightGBM feature importance matrix + holdout AUC from saved ranker artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hibs_racing.models.feature_importance import print_feature_importance_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="LightGBM ranker feature importance diagnostic")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of ASCII table")
    parser.add_argument("--config", type=Path, help="Path to ingest/config.yaml")
    args = parser.parse_args()
    try:
        print_feature_importance_report(config_path=args.config, as_json=args.json)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
