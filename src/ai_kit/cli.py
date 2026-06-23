"""AI Kit CLI — run, check, export, verify-bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ai_kit.pipeline import AgentLoop
from ai_kit.validate import validate_with_retry
from inst_spine.cli_util import run_cli
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.product_cli import (
    print_json,
    run_f9_check,
    run_institutional_export,
    run_institutional_verify,
)

PRODUCT = "ai-kit"


def _demo_validator(data: dict[str, Any]) -> dict[str, Any]:
    if "ok" not in data:
        raise ValueError("missing ok field")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai-kit")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run agent steps with checkpoint + trace ledger")
    p_run.add_argument("--agent-id", default="demo")
    p_run.add_argument("--steps", type=int, default=3)
    p_run.add_argument("--checkpoint-db", type=Path, default=None)
    p_run.add_argument("--trace-db", type=Path, default=Path("data/ai_kit_trace.sqlite"))
    p_run.add_argument("--max-tokens", type=int, default=1000, help="Token budget hint for limiter")

    p_check = sub.add_parser("check", help="F1–F9 on trace ledger")
    p_check.add_argument("--database", type=Path, default=Path("data/ai_kit_trace.sqlite"))

    p_export = sub.add_parser("export", help="Audit bundle from trace ledger")
    p_export.add_argument("--database", type=Path, default=Path("data/ai_kit_trace.sqlite"))
    p_export.add_argument("--out-dir", type=Path, default=None)
    p_export.add_argument("--tarball", type=Path, default=None)
    p_export.add_argument("--repro-check", action="store_true")

    p_bundle = sub.add_parser("verify-bundle", help="Offline auditor replay")
    p_bundle.add_argument("--tarball", type=Path, required=True)

    p_validate = sub.add_parser("validate-demo", help="Structured output validation demo")
    p_validate.add_argument("--raw", default='{"ok":true}')

    args = parser.parse_args(argv)

    if args.cmd == "run":
        trace = AppendOnlyLedger(args.trace_db, writer_id=args.agent_id)
        loop = AgentLoop(
            agent_id=args.agent_id,
            checkpoint_db=args.checkpoint_db,
            trace_ledger=trace,
        )

        def _step(step: int, state: dict[str, Any]) -> dict[str, Any]:
            raw = json.dumps({"ok": True, "step": step, "max_tokens": args.max_tokens})
            result = validate_with_retry(raw, _demo_validator, max_attempts=3)
            if not result.ok:
                raise ValueError(result.error or "validation failed")
            state = dict(state)
            state[f"step_{step}"] = result.value
            return state

        final = loop.run_steps(start_step=0, steps=args.steps, step_fn=_step)
        print_json({"product": PRODUCT, "final_state": final, "trace_db": str(args.trace_db)})
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

    if args.cmd == "validate-demo":
        result = validate_with_retry(args.raw, _demo_validator)
        print_json(
            {
                "ok": result.ok,
                "attempts": result.attempts,
                "error": result.error,
                "value": result.value,
            }
        )
        return 0 if result.ok else 1

    return 1


if __name__ == "__main__":
    run_cli(lambda: main())
