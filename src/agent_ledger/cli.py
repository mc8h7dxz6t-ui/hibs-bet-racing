"""Agent Ledger CLI — authorize tool calls before execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_ledger.gate import AgentActionGate, AgentActionRequest, gate_from_paths
from agent_ledger.policy import ToolPolicy
from inst_spine.cli_util import run_cli
from agent_ledger.export import build_agent_ledger_audit_bundle
from inst_spine.export import verify_bundle_reproducible
from inst_spine.product_cli import (
    print_json,
    run_f9_check,
    run_institutional_verify,
)

PRODUCT = "agent-ledger"


def _parse_json_object(raw: str, label: str) -> dict:
    p = Path(raw)
    data = json.loads(p.read_text(encoding="utf-8") if p.is_file() else raw)
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-ledger",
        description="Runtime agent tool authorization — permit before invoke, attest after",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_auth = sub.add_parser("authorize", help="Evaluate tool call before execution")
    p_auth.add_argument("--agent-id", required=True)
    p_auth.add_argument("--tool", required=True)
    p_auth.add_argument("--args", default="{}", help="JSON object of tool arguments")
    p_auth.add_argument("--session-id", default="")
    p_auth.add_argument("--idempotency-key", default=None)
    p_auth.add_argument("--database", type=Path, default=Path("data/agent_ledger.sqlite"))
    p_auth.add_argument("--permit-db", type=Path, default=None)
    p_auth.add_argument("--policy-file", type=Path, default=None)
    p_auth.add_argument("--shadow", action="store_true")

    p_complete = sub.add_parser("complete", help="Attest tool result against open permit")
    p_complete.add_argument("--permit-id", required=True)
    p_complete.add_argument("--result", default="{}", help="JSON result or inline string")
    p_complete.add_argument("--database", type=Path, default=Path("data/agent_ledger.sqlite"))
    p_complete.add_argument("--permit-db", type=Path, default=None)

    p_check = sub.add_parser("check", help="F1–F9 institutional check")
    p_check.add_argument("--database", type=Path, default=Path("data/agent_ledger.sqlite"))

    p_export = sub.add_parser("export", help="Deterministic audit bundle")
    p_export.add_argument("--database", type=Path, default=Path("data/agent_ledger.sqlite"))
    p_export.add_argument("--out-dir", type=Path, default=None)
    p_export.add_argument("--tarball", type=Path, default=None)
    p_export.add_argument("--repro-check", action="store_true")
    p_export.add_argument(
        "--observation-lane",
        action="store_true",
        default=True,
        help="Redact tool arguments in export bundle (default on)",
    )
    p_export.add_argument(
        "--no-observation-lane",
        action="store_false",
        dest="observation_lane",
        help="Include raw tool arguments in export bundle",
    )

    p_bundle = sub.add_parser("verify-bundle", help="Offline auditor replay")
    p_bundle.add_argument("--tarball", type=Path, required=True)

    p_serve = sub.add_parser("serve", help="HTTP authorize/complete API")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)

    args = parser.parse_args(argv)

    if args.cmd == "authorize":
        policy = ToolPolicy.from_file(args.policy_file) if args.policy_file else ToolPolicy()
        if args.shadow:
            policy.shadow_mode = True
        gw = gate_from_paths(
            ledger_db=args.database,
            permit_db=args.permit_db,
            policy=policy,
        )
        arguments = _parse_json_object(args.args, "args")
        resp = gw.authorize(
            AgentActionRequest(
                agent_id=args.agent_id,
                tool_name=args.tool,
                arguments=arguments,
                session_id=args.session_id,
                idempotency_key=args.idempotency_key,
            )
        )
        ok = resp.decision.value in ("permit", "escalate") or policy.shadow_mode
        print_json({"ok": ok, "product": PRODUCT, **resp.to_dict()})
        return 0 if resp.decision.value == "permit" or policy.shadow_mode else 1

    if args.cmd == "complete":
        gw = gate_from_paths(ledger_db=args.database, permit_db=args.permit_db)
        raw = args.result
        p = Path(raw)
        if p.is_file():
            result = json.loads(p.read_text(encoding="utf-8"))
        else:
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                result = raw
        resp = gw.complete(args.permit_id, result=result)
        print_json({"ok": resp.decision.value == "permit", "product": PRODUCT, **resp.to_dict()})
        return 0 if resp.decision.value == "permit" else 1

    if args.cmd == "check":
        code, body = run_f9_check(args.database)
        print_json(body)
        return code

    if args.cmd == "export":
        if args.repro_check:
            ok, msg = verify_bundle_reproducible(args.database)
            print_json({"ok": ok, "message": msg, "product": PRODUCT})
            return 0 if ok else 1
        result = build_agent_ledger_audit_bundle(
            args.database,
            out_dir=args.out_dir,
            tarball_path=args.tarball,
            observation_lane=args.observation_lane,
            product=PRODUCT,
        )
        body = {
            "ok": result.ok,
            "product": PRODUCT,
            "bundle_sha256": result.bundle_sha256,
            "tarball": str(result.tarball_path) if result.tarball_path else None,
            "validation": result.validation.message,
            "institutional_passed": result.institutional_passed,
            "observation_lane": args.observation_lane,
        }
        print_json(body)
        return 0 if result.ok else 1

    if args.cmd == "verify-bundle":
        code, body = run_institutional_verify(args.tarball, product=PRODUCT)
        print_json(body)
        return code

    if args.cmd == "serve":
        import os

        from agent_ledger.serve import main as serve_main

        if args.host:
            os.environ["AGENT_LEDGER_HOST"] = args.host
        if args.port:
            os.environ["AGENT_LEDGER_PORT"] = str(args.port)
        serve_main()
        return 0

    return 1


if __name__ == "__main__":
    run_cli(lambda: main())
