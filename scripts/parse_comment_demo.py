#!/usr/bin/env python3
"""Demo: reverse-engineer sectional pace proxies from running comments (no GPS)."""

from __future__ import annotations

import json
import sys

from hibs_racing.nlp.pipeline import parse_comment

EXAMPLES = [
    "held up, smooth headway 2f out, quickened to lead inside final furlong",
    "prominent, weakened inside final furlong",
    "hampered early, short of room 2f out, ran on well",
    "made all, finished fast",
]


def main() -> int:
    for text in EXAMPLES:
        features = parse_comment(text)
        print(text)
        print(json.dumps(features.elite_labels(), indent=2))
        print("-" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
