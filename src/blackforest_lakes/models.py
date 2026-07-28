"""Typed records shared across pipeline stages.

None of these types ever carry author name, author profile URL, or author
photo URL (GDPR requirement from the task brief) -- that data is stripped
in providers/google_places.py before a raw response is even cached, so it
never reaches these dataclasses in the first place.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlaceCandidate:
    """One Text Search hit for one lake query -- Stage 1 output, pre-confirmation."""

    lake_slug: str
    query: str
    rank: int
    place_id: str
    display_name: str
    formatted_address: str
    primary_type: str
    lat: float | None
    lng: float | None
    user_rating_count: int | None
    rating: float | None


@dataclass
class ResolvedPlace:
    """One confirmed lake -> place_id mapping, i.e. a row of data/place_ids.csv."""

    lake_slug: str
    lake_name_de: str
    place_id: str  # empty string if status == "unresolved"
    lat: float | None
    lng: float | None
    status: str  # "confirmed" | "unresolved"
    note: str = ""


@dataclass
class RawReview:
    """One review as returned by a ReviewProvider, PII already stripped."""

    place_id: str
    rating: float | None
    text_original: str
    lang_reported: str | None  # API-reported languageCode, may be None
    google_translated_text: str | None  # Google's own `text` field, if it differs from originalText
    google_translated_lang: str | None
    publish_time: str | None  # ISO 8601
    relative_time: str | None
    provider: str
    fetched_at: str  # ISO 8601, recorded once at first (non-cached) fetch


@dataclass
class ReviewRecord:
    """One output row: data/blackforest_lake_reviews.csv."""

    review_id: str
    lake_slug: str
    lake_name_de: str
    place_id: str
    lat: float | None
    lng: float | None
    lake_total_ratings: int | None
    lake_mean_rating: float | None
    rating: float | None
    text_original: str
    lang_detected: str
    lang_reported: str | None
    text_en: str
    translation_source: str  # "deepl" | "anthropic" | "none_already_en" | "google_native"
    publish_time: str | None
    relative_time: str | None
    provider: str
    fetched_at: str


OUTPUT_FIELDNAMES = [
    "review_id",
    "lake_slug",
    "lake_name_de",
    "place_id",
    "lat",
    "lng",
    "lake_total_ratings",
    "lake_mean_rating",
    "rating",
    "text_original",
    "lang_detected",
    "lang_reported",
    "text_en",
    "translation_source",
    "publish_time",
    "relative_time",
    "provider",
    "fetched_at",
]
