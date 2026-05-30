from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def parallel_map(
    items: list[T],
    fn: Callable[[T], R],
    *,
    max_workers: int = 4,
) -> list[R]:
    """Run fn over items in a thread pool; preserves input order."""
    if not items:
        return []
    workers = max(1, min(max_workers, len(items)))
    if workers == 1:
        return [fn(item) for item in items]
    results: list[R | None] = [None] * len(items)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, item): idx for idx, item in enumerate(items)}
        for fut in as_completed(futures):
            idx = futures[fut]
            results[idx] = fut.result()
    return [r for r in results if r is not None]


def timed_ms(fn: Callable[[], T]) -> tuple[T, float]:
    start = time.perf_counter()
    out = fn()
    return out, round((time.perf_counter() - start) * 1000, 1)
