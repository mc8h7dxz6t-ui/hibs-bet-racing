"""ModelGovernor CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from inst_spine.cli_util import run_cli
from inst_spine.errors import IngestValidationError
from inst_spine.product_cli import (
    print_json,
    run_f9_check,
    run_institutional_export,
    run_institutional_verify,
)
from model_governor.record import GOVERNANCE_ACTIONS, manifest_from_dict, record_governance_event

PRODUCT = "model-governor"


def _load_json(path_or_raw: str) -> dict:
    p = Path(path_or_raw)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return json.loads(path_or_raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="model-governor")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_record = sub.add_parser("record", help="Record a model governance event")
    p_record.add_argument(
        "--action",
        required=True,
        choices=sorted(GOVERNANCE_ACTIONS),
        help="Governance action",
    )
    p_record.add_argument("--model", required=True, help="Model snapshot JSON file or inline JSON")
    p_record.add_argument("--outcome", default="{}", help="Outcome JSON string or path")
    p_record.add_argument("--actor", default="model-governor")
    p_record.add_argument("--manifest", type=Path, default=None)
    p_record.add_argument("--database", type=Path, default=Path("data/model_governor.sqlite"))

    p_check = sub.add_parser("check", help="F1–F9 institutional check")
    p_check.add_argument("--database", type=Path, default=Path("data/model_governor.sqlite"))

    p_export = sub.add_parser("export", help="Deterministic audit bundle")
    p_export.add_argument("--database", type=Path, default=Path("data/model_governor.sqlite"))
    p_export.add_argument("--out-dir", type=Path, default=None)
    p_export.add_argument("--tarball", type=Path, default=None)
    p_export.add_argument("--repro-check", action="store_true")

    p_bundle = sub.add_parser("verify-bundle", help="Offline auditor replay")
    p_bundle.add_argument("--tarball", type=Path, required=True)

    args = parser.parse_args(argv)

    if args.cmd == "record":
        snap = _load_json(args.model)
        if not isinstance(snap, dict):
            raise IngestValidationError("--model must be a JSON object")
        outcome = _load_json(args.outcome)
        manifest = None
        if args.manifest is not None:
            manifest = manifest_from_dict(
                json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            )
        entry = record_governance_event(
            action=args.action,
            model_snapshot=snap,
            outcome=outcome,
            actor=args.actor,
            manifest=manifest,
            database=args.database,
        )
        print_json({"ok": True, "entry": entry, "product": PRODUCT})
        return 0

    if args.cmd == "check":
        code, body = run_f9_check(args.database)
        print_json(body)
        return code

    if args.cmd == "export":
        code, body = run_institutional_export(
            args.database,
            product=PRODUCT,
            out_dir=args.out_dir,
            tarball=args.tarball,
            repro_check=args.repro_check,
        )
        print_json(body)
        return code

    if args.cmd == "verify-bundle":
        code, body = run_institutional_verify(args.tarball, product=PRODUCT)
        print_json(body)
        return code

    return 1


if __name__ == "__main__":
    run_cli(lambda: main())
