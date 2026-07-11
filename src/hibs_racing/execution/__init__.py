"""Execution guards — slippage / EV burn protection."""

from hibs_racing.execution.slippage_guard import (
    ExecutionState,
    SlippageVerdict,
    evaluate_fill_slippage,
)

__all__ = [
    "ExecutionState",
    "SlippageVerdict",
    "evaluate_fill_slippage",
]
