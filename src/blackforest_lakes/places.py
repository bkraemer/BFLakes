"""Stage 1: resolve each lake name to a Google Places place_id.

This module only ever performs Text Search (place discovery). It never
fetches reviews -- that is Stage 2, and Stage 2 must not run until a human
has confirmed data/place_ids.csv (see cli.py `resolve-places confirm`).
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from . import config
from .cache import RequestCounter, read_json_cache, write_json_cache
from .lakes import LAKE_TARGETS, LakeTarget, location_bias_circle
from .models import PlaceCandidate, ResolvedPlace
from .retry import request_with_retry

logger = logging.getLogger("blackforest_lakes")

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.primaryType",
        "places.location",
        "places.userRatingCount",
        "places.rating",
    ]
)

CANDIDATE_FIELDNAMES = [
    "lake_slug",
    "query",
    "rank",
    "display_name",
    "formatted_address",
    "place_id",
    "primary_type",
    "lat",
    "lng",
    "user_rating_count",
    "rating",
    "selected",
    "note",
]


def search_lake(
    target: LakeTarget,
    api_key: str,
    counter: RequestCounter,
    *,
    force: bool = False,
) -> list[PlaceCandidate]:
    """Text Search for one lake, caching the raw response to data/raw/places_search/."""
    cache_path = config.PLACES_SEARCH_RAW_DIR / f"{target.slug}.json"
    payload = None if force else read_json_cache(cache_path)

    if payload is None:
        response = request_with_retry(
            "POST",
            TEXT_SEARCH_URL,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": FIELD_MASK,
            },
            json={
                "textQuery": target.query,
                "locationBias": location_bias_circle(),
            },
            timeout=30,
        )
        counter.add("places_text_search")
        payload = response.json()
        write_json_cache(cache_path, payload)
    else:
        logger.info("Using cached Text Search response for %s", target.slug)

    candidates = []
    for rank, place in enumerate(payload.get("places", []), start=1):
        location = place.get("location", {})
        candidates.append(
            PlaceCandidate(
                lake_slug=target.slug,
                query=target.query,
                rank=rank,
                place_id=place.get("id", ""),
                display_name=place.get("displayName", {}).get("text", ""),
                formatted_address=place.get("formattedAddress", ""),
                primary_type=place.get("primaryType", ""),
                lat=location.get("latitude"),
                lng=location.get("longitude"),
                user_rating_count=place.get("userRatingCount"),
                rating=place.get("rating"),
            )
        )
    return candidates


def search_all_lakes(api_key: str, counter: RequestCounter, *, force: bool = False) -> list[PlaceCandidate]:
    all_candidates: list[PlaceCandidate] = []
    for target in LAKE_TARGETS:
        candidates = search_lake(target, api_key, counter, force=force)
        if not candidates:
            logger.warning("No Text Search candidates found for %s (%r)", target.slug, target.query)
        all_candidates.extend(candidates)
    return all_candidates


def print_candidate_table(candidates: list[PlaceCandidate]) -> None:
    header = (
        f"{'lake_slug':<20} {'rank':<4} {'displayName':<28} {'primaryType':<20} "
        f"{'lat':<9} {'lng':<9} {'ratings':<8} {'rating':<6} place_id"
    )
    print(header)
    print("-" * len(header))
    for c in candidates:
        print(
            f"{c.lake_slug:<20} {c.rank:<4} {c.display_name[:28]:<28} {c.primary_type[:20]:<20} "
            f"{c.lat if c.lat is not None else '':<9} {c.lng if c.lng is not None else '':<9} "
            f"{c.user_rating_count if c.user_rating_count is not None else '':<8} "
            f"{c.rating if c.rating is not None else '':<6} {c.place_id}"
        )
        if c.formatted_address:
            print(f"{'':<20} {'':<4} address: {c.formatted_address}")


def write_candidates_csv(candidates: list[PlaceCandidate], path: Path = config.PLACE_ID_CANDIDATES_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    notes_by_slug = {t.slug: t.note for t in LAKE_TARGETS}
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANDIDATE_FIELDNAMES)
        writer.writeheader()
        seen_slugs = set()
        for c in candidates:
            seen_slugs.add(c.lake_slug)
            writer.writerow(
                {
                    "lake_slug": c.lake_slug,
                    "query": c.query,
                    "rank": c.rank,
                    "display_name": c.display_name,
                    "formatted_address": c.formatted_address,
                    "place_id": c.place_id,
                    "primary_type": c.primary_type,
                    "lat": c.lat,
                    "lng": c.lng,
                    "user_rating_count": c.user_rating_count,
                    "rating": c.rating,
                    "selected": "",
                    "note": notes_by_slug.get(c.lake_slug, ""),
                }
            )
        # Lakes with zero Text Search hits still get a row so `confirm` can see them.
        for target in LAKE_TARGETS:
            if target.slug not in seen_slugs:
                writer.writerow(
                    {
                        "lake_slug": target.slug,
                        "query": target.query,
                        "rank": "",
                        "display_name": "",
                        "formatted_address": "",
                        "place_id": "",
                        "primary_type": "",
                        "lat": "",
                        "lng": "",
                        "user_rating_count": "",
                        "rating": "",
                        "selected": "",
                        "note": target.note,
                    }
                )
    logger.info("Wrote %d candidate rows to %s", len(candidates), path)


_TRUE_VALUES = {"1", "true", "yes", "y", "x"}


def confirm_mapping(
    candidates_path: Path = config.PLACE_ID_CANDIDATES_CSV,
    output_path: Path = config.PLACE_IDS_CSV,
) -> list[ResolvedPlace]:
    """Turn a human-annotated candidates CSV into the confirmed data/place_ids.csv.

    The human reviews the printed table / candidates CSV from `search`, then
    edits the `selected` column of the candidates CSV: mark exactly one row
    per lake with 1/true/yes/x to confirm it as the natural-feature match.
    A lake with zero selected rows is written as "unresolved" rather than
    guessing -- per the task brief, do not substitute a nearby business.
    """
    if not candidates_path.exists():
        raise FileNotFoundError(
            f"{candidates_path} not found. Run `bfl resolve-places search` first."
        )

    rows_by_slug: dict[str, list[dict]] = {}
    with candidates_path.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows_by_slug.setdefault(row["lake_slug"], []).append(row)

    resolved: list[ResolvedPlace] = []
    errors: list[str] = []

    for target in LAKE_TARGETS:
        rows = rows_by_slug.get(target.slug, [])
        selected = [r for r in rows if r.get("selected", "").strip().lower() in _TRUE_VALUES]

        if len(selected) > 1:
            errors.append(
                f"{target.slug}: {len(selected)} rows marked selected, expected exactly 1 "
                f"(place_ids: {[r['place_id'] for r in selected]})"
            )
            continue

        if not selected:
            resolved.append(
                ResolvedPlace(
                    lake_slug=target.slug,
                    lake_name_de="",
                    place_id="",
                    lat=None,
                    lng=None,
                    status="unresolved",
                    note=target.note or "No candidate selected in confirm step.",
                )
            )
            continue

        row = selected[0]
        resolved.append(
            ResolvedPlace(
                lake_slug=target.slug,
                lake_name_de=row["display_name"],
                place_id=row["place_id"],
                lat=float(row["lat"]) if row.get("lat") else None,
                lng=float(row["lng"]) if row.get("lng") else None,
                status="confirmed",
                note=target.note,
            )
        )

    if errors:
        raise ValueError(
            "Ambiguous confirmation, fix data/place_id_candidates.csv and rerun:\n"
            + "\n".join(errors)
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["lake_slug", "lake_name_de", "place_id", "lat", "lng", "status", "note"]
        )
        writer.writeheader()
        for r in resolved:
            writer.writerow(
                {
                    "lake_slug": r.lake_slug,
                    "lake_name_de": r.lake_name_de,
                    "place_id": r.place_id,
                    "lat": r.lat,
                    "lng": r.lng,
                    "status": r.status,
                    "note": r.note,
                }
            )

    n_confirmed = sum(1 for r in resolved if r.status == "confirmed")
    n_unresolved = len(resolved) - n_confirmed
    logger.info(
        "Wrote %s: %d confirmed, %d unresolved", output_path, n_confirmed, n_unresolved
    )
    return resolved


def load_confirmed_places(path: Path = config.PLACE_IDS_CSV) -> list[ResolvedPlace]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `bfl resolve-places search` then "
            f"`bfl resolve-places confirm` first (Stage 1 requires human review)."
        )
    places = []
    with path.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            places.append(
                ResolvedPlace(
                    lake_slug=row["lake_slug"],
                    lake_name_de=row["lake_name_de"],
                    place_id=row["place_id"],
                    lat=float(row["lat"]) if row.get("lat") else None,
                    lng=float(row["lng"]) if row.get("lng") else None,
                    status=row["status"],
                    note=row.get("note", ""),
                )
            )
    return places
