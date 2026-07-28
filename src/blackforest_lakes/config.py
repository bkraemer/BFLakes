"""Environment / configuration loading.

All secrets come from the environment (optionally via a local .env file).
Nothing is hardcoded and nothing is logged.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PLACES_SEARCH_RAW_DIR = RAW_DIR / "places_search"
PLACE_DETAILS_RAW_DIR = RAW_DIR / "place_details"
CACHE_DIR = DATA_DIR / "cache"
LOG_DIR = DATA_DIR / "logs"

PLACE_ID_CANDIDATES_CSV = DATA_DIR / "place_id_candidates.csv"
PLACE_IDS_CSV = DATA_DIR / "place_ids.csv"
OUTPUT_CSV = DATA_DIR / "blackforest_lake_reviews.csv"
COVERAGE_CSV = DATA_DIR / "coverage_report.csv"
REQUEST_LOG_CSV = DATA_DIR / "request_log.csv"
TRANSLATION_CACHE_DB = CACHE_DIR / "translations.sqlite3"

_dotenv_loaded = False


def _ensure_dotenv() -> None:
    global _dotenv_loaded
    if not _dotenv_loaded:
        load_dotenv(REPO_ROOT / ".env")
        _dotenv_loaded = True


def get_env(name: str, *, required: bool = False) -> str | None:
    """Read an environment variable, loading .env on first use.

    Raises RuntimeError (not at import time) if a required variable is
    missing, so importing this module never requires credentials to exist.
    """
    _ensure_dotenv()
    value = os.environ.get(name)
    if value is not None:
        value = value.strip() or None
    if required and not value:
        raise RuntimeError(
            f"{name} is not set. Copy .env.example to .env and fill it in, "
            f"or export {name} in your shell."
        )
    return value


def google_maps_api_key(*, required: bool = True) -> str | None:
    return get_env("GOOGLE_MAPS_API_KEY", required=required)


def deepl_api_key() -> str | None:
    return get_env("DEEPL_API_KEY", required=False)


def anthropic_api_key(*, required: bool = True) -> str | None:
    return get_env("ANTHROPIC_API_KEY", required=required)


def ensure_data_dirs() -> None:
    for d in (
        DATA_DIR,
        RAW_DIR,
        PLACES_SEARCH_RAW_DIR,
        PLACE_DETAILS_RAW_DIR,
        CACHE_DIR,
        LOG_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
