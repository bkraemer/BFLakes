"""Stage 2 orchestration: fetch reviews for every confirmed place."""
from __future__ import annotations

import logging

from .cache import RequestCounter
from .models import ResolvedPlace
from .providers.base import PlaceReviews, ReviewProvider

logger = logging.getLogger("blackforest_lakes")


def fetch_all_places(
    places: list[ResolvedPlace],
    provider: ReviewProvider,
    *,
    force: bool = False,
) -> dict[str, PlaceReviews]:
    """Fetch reviews for every confirmed (status == "confirmed") place.

    Unresolved lakes are skipped with a warning rather than guessed at --
    Stage 1 already refused to substitute a nearby business for them.
    """
    results: dict[str, PlaceReviews] = {}
    for place in places:
        if place.status != "confirmed":
            logger.warning(
                "Skipping unresolved lake %s (no confirmed place_id)", place.lake_slug
            )
            continue
        results[place.place_id] = provider.fetch_reviews(place.place_id, force=force)
    return results
