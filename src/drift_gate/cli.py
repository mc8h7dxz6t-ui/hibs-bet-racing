"""Drift Gate CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from inst_spine.cli_util import run_cli
from inst_spine.product_cli import (
    print_json,
    run_f9_check,
    run_institutional_export,
    run_institutional_verify,
)

from drift_gate.baseline import FeatureBaseline
from drift_gate.gate import DriftGate, DriftGateConfig, DriftGateMode, DriftGateRequest
from drift_gate.record import record_drift_evaluation
from drift_gate.state import RollingStateStore

PRODUCT = "drift-gate"


def _load_json(path_or_raw: str) -> dict:
    p = Path(path_or_raw)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return json.loads(path_or_raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="drift-gate")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_baseline = sub.add_parser("baseline", help="Create or extend a feature baseline")
    p_baseline.add_argument("--model-id", required=True)
    p_baseline.add_argument("--version", default="v1")
    p_baseline.add_argument("--features", required=True, help="JSON file or inline feature vector")
    p_baseline.add_argument("--out", type=Path, required=True)
    p_baseline.add_argument("--samples", type=int, default=50, help="Synthetic samples if --synthetic")
    p_baseline.add_argument("--synthetic", action="store_true", help="Generate synthetic baseline from means")

    p_eval = sub.add_parser("evaluate", help="Evaluate one feature vector against baseline")
    p_eval.add_argument("--baseline", type=Path, required=True)
    p_eval.add_argument("--state", type=Path, default=None, help="Rolling window state (default: <baseline>.rolling.json)")
    p_eval.add_argument("--model-id", default=None)
    p_eval.add_argument("--version", default=None)
    p_eval.add_argument("--features", required=True)
    p_eval.add_argument("--mode", choices=["shadow", "enforce"], default="shadow")
    p_eval.add_argument("--database", type=Path, default=None)
    p_eval.add_argument("--request-id", default="")
    p_eval.add_argument("--no-record", action="store_true")

    p_check = sub.add_parser("check", help="F1–F9 institutional check")
    p_check.add_argument("--database", type=Path, default=Path("data/drift_gate.sqlite"))

    p_export = sub.add_parser("export", help="Deterministic audit bundle")
    p_export.add_argument("--database", type=Path, default=Path("data/drift_gate.sqlite"))
    p_export.add_argument("--out-dir", type=Path, default=None)
    p_export.add_argument("--tarball", type=Path, default=None)
    p_export.add_argument("--repro-check", action="store_true")

    p_bundle = sub.add_parser("verify-bundle", help="Offline auditor replay")
    p_bundle.add_argument("--tarball", type=Path, required=True)

    args = parser.parse_args(argv)

    if args.cmd == "baseline":
        feats = _load_json(args.features)
        bl = FeatureBaseline(model_id=args.model_id, version=args.version)
        if args.synthetic:
            import random

            random.seed(42)
            for name, mean in feats.items():
                m = float(mean)
                bl.features[name] = [m + random.gauss(0, m * 0.05) for _ in range(args.samples)]
        else:
            bl.add_sample({k: float(v) for k, v in feats.items()})
        bl.save(args.out)
        print_json({"ok": True, "baseline": str(args.out), "features": list(bl.features.keys())})
        return 0

    if args.cmd == "evaluate":
        bl = FeatureBaseline.load(args.baseline)
        features = _load_json(args.features)
        feature_vector = {k: float(v) for k, v in features.items()}
        rolling = RollingStateStore.from_baseline(
            args.baseline,
            state_path=args.state,
            redis_key=args.model_id or bl.model_id,
        )
        gate = DriftGate(
            bl,
            config=DriftGateConfig(mode=DriftGateMode(args.mode)),
            rolling_window=rolling.as_dict(),
        )
        req = DriftGateRequest(
            model_id=args.model_id or bl.model_id,
            version=args.version or bl.version,
            feature_vector=feature_vector,
            request_id=args.request_id,
        )
        resp = gate.evaluate(req)
        rolling._data = gate._rolling
        rolling.save()
        body: dict = {"ok": True, "product": PRODUCT, **resp.to_dict()}
        if not args.no_record and args.database is not None:
            entry = record_drift_evaluation(request=req, response=resp, database=args.database)
            body["ledger_entry"] = entry
        elif not args.no_record:
            entry = record_drift_evaluation(request=req, response=resp)
            body["ledger_entry"] = entry
        print_json(body)
        return 0 if resp.decision.value == "approve" else 1

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
