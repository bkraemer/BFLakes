"""Turns fetched reviews into the two deliverable CSVs, translating along the way.

Idempotent: review_id is a stable hash of (place_id, publish_time, text), so
rerunning the pipeline against the same cached raw responses reproduces the
same review_ids and merge_rows() overwrites in place rather than
duplicating. Translations are cached separately (translation_cache.py) so
rerunning never re-translates already-seen text.
"""
from __future__ import annotations

import csv
import hashlib
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .cache import RequestCounter
from .models import OUTPUT_FIELDNAMES, ResolvedPlace
from .providers.base import PlaceReviews
from .translate import translate_review
from .translation_cache import TranslationCache

logger = logging.getLogger("blackforest_lakes")


def make_review_id(place_id: str, publish_time: str | None, text: str) -> str:
    raw = f"{place_id}|{publish_time or ''}|{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_rows(
    places: list[ResolvedPlace],
    place_reviews: dict[str, PlaceReviews],
    *,
    translation_cache: TranslationCache,
    counter: RequestCounter,
    deepl_api_key: str | None,
    anthropic_api_key: str | None,
) -> list[dict]:
    places_by_id = {p.place_id: p for p in places if p.status == "confirmed"}
    rows: list[dict] = []

    for place_id, pr in place_reviews.items():
        place = places_by_id[place_id]
        for review in pr.reviews:
            lang_detected, text_en, translation_source = translate_review(
                review.text_original,
                cache=translation_cache,
                counter=counter,
                deepl_api_key=deepl_api_key,
                anthropic_api_key=anthropic_api_key,
            )
            review_id = make_review_id(place_id, review.publish_time, review.text_original)
            rows.append(
                {
                    "review_id": review_id,
                    "lake_slug": place.lake_slug,
                    "lake_name_de": pr.display_name or place.lake_name_de,
                    "place_id": place_id,
                    "lat": place.lat,
                    "lng": place.lng,
                    "lake_total_ratings": pr.user_rating_count,
                    "lake_mean_rating": pr.rating,
                    "rating": review.rating,
                    "text_original": review.text_original,
                    "lang_detected": lang_detected,
                    "lang_reported": review.lang_reported,
                    "text_en": text_en,
                    "translation_source": translation_source,
                    "publish_time": review.publish_time,
                    "relative_time": review.relative_time,
                    "provider": review.provider,
                    "fetched_at": review.fetched_at,
                }
            )
    return rows


def merge_rows(existing_rows: list[dict], new_rows: list[dict]) -> list[dict]:
    """Upsert by review_id -- reruns overwrite in place, never duplicate."""
    by_id = {r["review_id"]: r for r in existing_rows}
    for r in new_rows:
        by_id[r["review_id"]] = r
    return sorted(by_id.values(), key=lambda r: (r["lake_slug"], r["publish_time"] or "", r["review_id"]))


def read_existing_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_output_csv(rows: list[dict], path: Path = config.OUTPUT_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in OUTPUT_FIELDNAMES})
    logger.info("Wrote %d review rows to %s", len(rows), path)


def write_coverage_report(
    places: list[ResolvedPlace],
    place_reviews: dict[str, PlaceReviews],
    rows: list[dict],
    path: Path = config.COVERAGE_CSV,
) -> None:
    """Per-lake sampling-bias documentation: retrieved vs. userRatingCount,
    text-bearing fraction, language breakdown, and date range covered."""
    rows_by_lake: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        rows_by_lake[r["lake_slug"]].append(r)

    fieldnames = [
        "lake_slug",
        "lake_name_de",
        "status",
        "place_id",
        "reviews_retrieved",
        "lake_total_ratings",
        "text_bearing_fraction",
        "language_breakdown",
        "earliest_publish_time",
        "latest_publish_time",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for place in places:
            lake_rows = rows_by_lake.get(place.lake_slug, [])
            pr = place_reviews.get(place.place_id) if place.status == "confirmed" else None

            n_retrieved = len(lake_rows)
            n_text_bearing = sum(1 for r in lake_rows if r["text_original"].strip())
            text_bearing_fraction = (n_text_bearing / n_retrieved) if n_retrieved else ""

            lang_counts = Counter(r["lang_detected"] for r in lake_rows)
            lang_breakdown = ";".join(f"{lang}:{n}" for lang, n in sorted(lang_counts.items()))

            publish_times = sorted(r["publish_time"] for r in lake_rows if r["publish_time"])

            writer.writerow(
                {
                    "lake_slug": place.lake_slug,
                    "lake_name_de": (pr.display_name if pr else "") or place.lake_name_de,
                    "status": place.status,
                    "place_id": place.place_id,
                    "reviews_retrieved": n_retrieved,
                    "lake_total_ratings": pr.user_rating_count if pr else "",
                    "text_bearing_fraction": (
                        f"{text_bearing_fraction:.3f}" if text_bearing_fraction != "" else ""
                    ),
                    "language_breakdown": lang_breakdown,
                    "earliest_publish_time": publish_times[0] if publish_times else "",
                    "latest_publish_time": publish_times[-1] if publish_times else "",
                }
            )
    logger.info("Wrote coverage report to %s", path)
