"""Stub ReviewProvider for a paid review aggregator (Outscraper / SerpApi / Apify).

Unlike GooglePlacesProvider, these services scrape or license Google Maps
reviews directly and return the FULL review set per place (not capped at 5,
not filtered to "most relevant"), at a per-place or per-review cost.

TODO(paid-provider): implement fetch_reviews() against whichever vendor is
chosen. It must:
  - accept the vendor API key from the environment (never hardcode it),
  - cache the raw vendor response to data/raw/ just like GooglePlacesProvider,
  - strip author name / profile URL / photo URL before caching or returning
    anything (see pii.py -- the same GDPR constraint applies here),
  - return PlaceReviews with the same RawReview schema so Stage 3 and the
    output builder work unchanged,
  - set RawReview.provider to the vendor name (e.g. "outscraper"), which
    flows through to the `provider` column of the final CSV,
  - use retry.request_with_retry (or equivalent) for 429/5xx backoff.
"""
from __future__ import annotations

from .base import PlaceReviews, ReviewProvider


class PaidProvider(ReviewProvider):
    name = "paid_provider_stub"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def fetch_reviews(self, place_id: str, *, force: bool = False) -> PlaceReviews:
        raise NotImplementedError(
            "PaidProvider is a seam, not an implementation. See the TODO in "
            "providers/paid_stub.py to wire up Outscraper/SerpApi/Apify."
        )
