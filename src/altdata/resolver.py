"""Cascade field resolution across ladder rungs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from altdata.ladders import FIELD_LADDERS, Fetcher, default_fetchers, fetch_url_context, http_fetchers


@dataclass
class ResolveResult:
    field: str
    value: Any
    source: str | None
    rung: int | None
    rescue: bool = False
    attempts: list[str] = field(default_factory=list)


class FieldResolver:
    def __init__(
        self,
        *,
        ladders: dict[str, list[str]] | None = None,
        fetchers: dict[str, Fetcher] | None = None,
    ) -> None:
        self.ladders = ladders or FIELD_LADDERS
        self.fetchers = fetchers or default_fetchers()

    def resolve(self, field: str, ctx: dict[str, Any]) -> ResolveResult:
        rungs = self.ladders.get(field, [])
        attempts: list[str] = []
        for idx, source_id in enumerate(rungs, start=1):
            attempts.append(source_id)
            fetcher = self.fetchers.get(source_id)
            if fetcher is None:
                continue
            try:
                val = fetcher(field, ctx)
            except Exception:
                continue
            if val is not None and val != "":
                return ResolveResult(
                    field=field,
                    value=val,
                    source=source_id,
                    rung=idx,
                    rescue=source_id == "structural_rescue",
                    attempts=attempts,
                )
        return ResolveResult(field=field, value=None, source=None, rung=None, attempts=attempts)

    def resolve_record(self, fields: list[str], ctx: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        meta: dict[str, Any] = {"sources": {}, "rescue_fields": []}
        for f in fields:
            r = self.resolve(f, ctx)
            out[f] = r.value
            if r.source:
                meta["sources"][f] = r.source
            if r.rescue:
                meta["rescue_fields"].append(f)
        out["_meta"] = meta
        return out

    def coverage_pct(self, record: dict[str, Any], fields: list[str]) -> float:
        if not fields:
            return 100.0
        filled = sum(1 for f in fields if record.get(f) is not None)
        return 100.0 * filled / len(fields)
