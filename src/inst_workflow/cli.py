"""Inst++ Workflow UI CLI."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _use_uvloop() -> None:
    try:
        import uvloop

        uvloop.install()
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="inst-workflow",
        description="Inst++ guided workflow console — Compliance Logger + Proxy-Risk",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_serve = sub.add_parser("serve", help="Start workflow UI server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8790)
    p_serve.add_argument(
        "--compliance-db",
        type=Path,
        default=Path(os.getenv("INST_COMPLIANCE_DB", "data/demo/compliance.sqlite")),
    )
    p_serve.add_argument(
        "--proxy-db",
        type=Path,
        default=Path(os.getenv("INST_PROXY_DB", "data/demo/proxy.sqlite")),
    )
    p_serve.add_argument(
        "--export-dir",
        type=Path,
        default=Path(os.getenv("INST_EXPORT_DIR", "data/demo/ui_exports")),
    )
    p_serve.add_argument(
        "--no-shadow",
        action="store_true",
        help="Disable proxy shadow mode by default",
    )

    args = parser.parse_args(argv)

    if args.cmd == "serve":
        _use_uvloop()
        import uvicorn

        from inst_workflow import serve

        serve.state.compliance_db = args.compliance_db
        serve.state.proxy_db = args.proxy_db
        serve.state.export_dir = args.export_dir
        serve.state.proxy_shadow = not args.no_shadow

        print(f"Inst++ Workflow Console → http://{args.host}:{args.port}")
        uvicorn.run(serve.app, host=args.host, port=args.port, log_level="info")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
