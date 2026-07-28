"""The ReviewProvider interface.

Any source of Google-Maps-style reviews (the free Places API, or a paid
scraping/aggregation service) implements this interface and returns the
same PlaceReviews schema, so Stage 3 (translate) and the output builder
never need to know which provider produced the data.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..models import RawReview


@dataclass
class PlaceReviews:
    """Everything Stage 2 needs about one place: its metadata plus reviews."""

    place_id: str
    display_name: str
    rating: float | None
    user_rating_count: int | None
    reviews: list[RawReview]
    raw_response: dict  # PII-stripped, cached verbatim to data/raw/


class ReviewProvider(ABC):
    """Fetches reviews for one place_id. Implementations must never return
    author name, author profile URL, or author photo URL (GDPR)."""

    name: str

    @abstractmethod
    def fetch_reviews(self, place_id: str, *, force: bool = False) -> PlaceReviews:
        """force=True bypasses the raw-response cache and refetches."""
        raise NotImplementedError
