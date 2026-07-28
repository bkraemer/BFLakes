"""Logging setup and the per-run billing ledger (data/request_log.csv)."""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone

from . import config

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(stage: str) -> logging.Logger:
    config.ensure_data_dirs()
    logger = logging.getLogger("blackforest_lakes")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_LOG_FORMAT))
    logger.addHandler(console)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = config.LOG_DIR / f"{timestamp}_{stage}.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logger.addHandler(file_handler)

    logger.info("Logging to %s", log_path)
    return logger


def append_request_log(stage: str, counts: dict) -> None:
    """Append one row to data/request_log.csv so API usage is auditable across runs."""
    config.ensure_data_dirs()
    path = config.REQUEST_LOG_CSV
    is_new = not path.exists()
    fieldnames = ["timestamp", "stage", "counts_json"]

    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if is_new:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": stage,
                "counts_json": json.dumps(counts, sort_keys=True),
            }
        )
