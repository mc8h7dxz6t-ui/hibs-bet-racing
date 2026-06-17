"""CLI entry for webhook mesh HTTP server."""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Inst++ Webhook Idempotency Mesh")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument(
        "--wal",
        default=None,
        help="WAL path (or INST_WAL_PATH env)",
    )
    args = parser.parse_args()
    if args.wal:
        os.environ["INST_WAL_PATH"] = args.wal
    import uvicorn

    uvicorn.run(
        "webhook_mesh.serve:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
