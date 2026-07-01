"""AI Kit CLI — run, check, export, verify-bundle."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from ai_kit.llm import OpenAICompatibleClient
from ai_kit.pipeline import AgentLoop
from ai_kit.validate import validate_with_retry
from inst_spine.cli_util import run_cli
from inst_spine.errors import InstError
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
    p_run.add_argument("--agent-ledger-db", type=Path, default=None, help="Agent Ledger integration")
    p_run.add_argument("--agent-permit-db", type=Path, default=None)
    p_run.add_argument("--tool-name", default="read_file", help="Tool to authorize via Agent Ledger")
    p_run.add_argument("--max-tokens", type=int, default=1000, help="Token budget hint for limiter")
    p_run.add_argument(
        "--live-llm",
        action="store_true",
        help="Call OpenAI-compatible API (requires OPENAI_API_KEY)",
    )
    p_run.add_argument("--prompt", default="Return JSON with ok:true and a one-line summary.")

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
            agent_ledger_db=args.agent_ledger_db,
            agent_permit_db=args.agent_permit_db,
        )
        llm = OpenAICompatibleClient()

        def _step(step: int, state: dict[str, Any]) -> dict[str, Any]:
            if args.live_llm:
                if not llm.configured:
                    raise InstError(
                        code="LLM_NOT_CONFIGURED",
                        message="OPENAI_API_KEY required for --live-llm",
                    )
                resp = llm.chat_json(
                    system='Respond with JSON only: {"ok": true, "summary": "..."}',
                    user=f"{args.prompt} (step {step})",
                    max_tokens=min(args.max_tokens, 512),
                )
                if not resp.ok or resp.parsed is None:
                    raise ValueError(resp.error or "LLM call failed")
                result = validate_with_retry(
                    json.dumps(resp.parsed),
                    _demo_validator,
                    max_attempts=1,
                )
                if not result.ok:
                    raise ValueError(result.error or "validation failed")
                value = {**result.value, "llm": True, "step": step, "model": llm.model}
            else:
                raw = json.dumps({"ok": True, "step": step, "max_tokens": args.max_tokens})
                result = validate_with_retry(raw, _demo_validator, max_attempts=3)
                if not result.ok:
                    raise ValueError(result.error or "validation failed")
                value = result.value
            state = dict(state)
            state[f"step_{step}"] = value
            return state

        final = loop.run_steps(
            start_step=0,
            steps=args.steps,
            step_fn=_step,
            tool_name=args.tool_name if args.agent_ledger_db else None,
            tool_arguments={"path": "docs/demo_snapshot.json"} if args.agent_ledger_db else None,
        )
        print_json(
            {
                "product": PRODUCT,
                "final_state": final,
                "trace_db": str(args.trace_db),
                "live_llm": args.live_llm and llm.configured,
            }
        )
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
