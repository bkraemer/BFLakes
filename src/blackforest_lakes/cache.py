"""Raw API response cache and per-run request counters.

Caching raw responses to data/raw/ means development reruns never refetch
(idempotent, and free of charge) unless --force is passed.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path

logger = logging.getLogger("blackforest_lakes")


def read_json_cache(path: Path) -> dict | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json_cache(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


class RequestCounter:
    """Accumulates API call / usage counts for one run, for billing visibility."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def add(self, key: str, n: int = 1) -> None:
        self.counts[key] += n

    def log_summary(self) -> None:
        if not self.counts:
            logger.info("Request summary: no API calls made this run.")
            return
        parts = ", ".join(f"{k}={v}" for k, v in sorted(self.counts.items()))
        logger.info("Request summary (for billing): %s", parts)

    def as_dict(self) -> dict:
        return dict(self.counts)
