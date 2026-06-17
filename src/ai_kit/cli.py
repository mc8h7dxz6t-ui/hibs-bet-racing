"""AI Kit CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ai_kit.pipeline import AgentLoop


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai-kit")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run demo agent steps with checkpointing")
    p_run.add_argument("--agent-id", default="demo")
    p_run.add_argument("--steps", type=int, default=3)
    p_run.add_argument("--checkpoint-db", type=Path)

    args = parser.parse_args(argv)

    if args.cmd == "run":
        loop = AgentLoop(agent_id=args.agent_id, checkpoint_db=args.checkpoint_db)

        def _step(step: int, state: dict) -> dict:
            state = dict(state)
            state[f"step_{step}"] = f"done_{step}"
            return state

        final = loop.run_steps(start_step=0, steps=args.steps, step_fn=_step)
        print(json.dumps(final, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
