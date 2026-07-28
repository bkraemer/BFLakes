"""Default ReviewProvider: Google Places API (New), Place Details.

IMPORTANT SAMPLING CAVEAT (also logged at fetch time, and documented in
README.md / coverage_report.csv): the Places API (New) `reviews` field
returns AT MOST 5 REVIEWS PER PLACE, and Google does not document or expose
how those 5 are chosen beyond calling them "the most relevant reviews" --
in practice this is believed to blend recency and helpfulness/prominence
signals, not a random sample. Any corpus built from this provider alone is
therefore a small, non-random, Google-curated subset of each place's
reviews, and coverage_report.csv's `text_bearing_fraction` documents just
how small a fraction of `userRatingCount` this typically is. Do not treat
n=5-per-place counts as representative of the full review population; that
requires PaidProvider (see paid_stub.py).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from .. import config
from ..cache import RequestCounter, read_json_cache, write_json_cache
from ..models import RawReview
from ..pii import strip_review_pii
from ..retry import request_with_retry
from .base import PlaceReviews, ReviewProvider

logger = logging.getLogger("blackforest_lakes")

PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

FIELD_MASK = ",".join(
    [
        "id",
        "displayName",
        "formattedAddress",
        "location",
        "rating",
        "userRatingCount",
        # `reviews`: capped at 5 by the API, "most relevant" selection -- see
        # module docstring. There is no parameter to request more or to
        # request a different (e.g. newest, random) ordering.
        "reviews",
    ]
)


class GooglePlacesProvider(ReviewProvider):
    name = "google_places"

    def __init__(self, api_key: str, counter: RequestCounter | None = None) -> None:
        self.api_key = api_key
        self.counter = counter or RequestCounter()

    def fetch_reviews(self, place_id: str, *, force: bool = False) -> PlaceReviews:
        cache_path = config.PLACE_DETAILS_RAW_DIR / f"{place_id}.json"
        payload = None if force else read_json_cache(cache_path)

        if payload is None:
            response = request_with_retry(
                "GET",
                PLACE_DETAILS_URL.format(place_id=place_id),
                headers={
                    "X-Goog-Api-Key": self.api_key,
                    "X-Goog-FieldMask": FIELD_MASK,
                },
                timeout=30,
            )
            self.counter.add("places_place_details")
            raw = response.json()
            # Strip author PII BEFORE caching to disk (GDPR) -- see pii.py.
            payload = strip_review_pii(raw)
            # Recorded once, at first fetch, so reruns from cache keep the
            # true fetch time rather than the time of the rerun.
            payload["_fetched_at"] = datetime.now(timezone.utc).isoformat()
            write_json_cache(cache_path, payload)
            n_reviews = len(payload.get("reviews", []))
            logger.info(
                "Fetched place_id=%s: %d/5-max reviews returned (Google's "
                "'most relevant' selection, not a random sample)",
                place_id,
                n_reviews,
            )
        else:
            logger.info("Using cached Place Details response for place_id=%s", place_id)

        fetched_at = payload.get("_fetched_at", datetime.now(timezone.utc).isoformat())
        reviews = [self._parse_review(place_id, r, fetched_at) for r in payload.get("reviews", [])]

        return PlaceReviews(
            place_id=place_id,
            display_name=payload.get("displayName", {}).get("text", ""),
            rating=payload.get("rating"),
            user_rating_count=payload.get("userRatingCount"),
            reviews=reviews,
            raw_response=payload,
        )

    def _parse_review(self, place_id: str, review: dict, fetched_at: str) -> RawReview:
        original = review.get("originalText") or review.get("text") or {}
        google_text = review.get("text") or {}

        # If Google's `text` differs from `originalText`, Google has already
        # auto-translated it for us. We still record that translation (as
        # google_translated_text/lang) but Stage 3 always runs our own
        # translation on originalText so the translation source is
        # consistent across the whole corpus (see translate.py).
        google_translated_text = None
        google_translated_lang = None
        if review.get("text") and review.get("originalText"):
            if google_text.get("text") != original.get("text"):
                google_translated_text = google_text.get("text")
                google_translated_lang = google_text.get("languageCode")

        return RawReview(
            place_id=place_id,
            rating=review.get("rating"),
            text_original=original.get("text", ""),
            lang_reported=original.get("languageCode"),
            google_translated_text=google_translated_text,
            google_translated_lang=google_translated_lang,
            publish_time=review.get("publishTime"),
            relative_time=review.get("relativePublishTimeDescription"),
            provider=self.name,
            fetched_at=fetched_at,
        )
