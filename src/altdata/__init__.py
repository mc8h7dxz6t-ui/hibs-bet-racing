"""Alt-Data extractors — one feed, four-rung field ladder."""

from altdata.poll import PollResult, poll_once
from altdata.resolver import FieldResolver

__all__ = ["FieldResolver", "PollResult", "poll_once"]
