"""GDPR guardrail: strip author PII from Places API responses.

The Places API (New) `reviews` field always includes a nested
`authorAttribution` object (displayName, uri, photoUri) -- there is no
field mask granular enough to exclude it server-side. This module removes
it immediately after the HTTP response is parsed and BEFORE the payload is
cached to disk or logged, so author name / profile URL / photo URL never
touch any intermediate file.
"""
from __future__ import annotations

_PII_KEYS = {"authorAttribution"}


def strip_review_pii(place_details_json: dict) -> dict:
    """Return a copy of a Place Details response with review author PII removed."""
    sanitized = dict(place_details_json)
    reviews = sanitized.get("reviews")
    if isinstance(reviews, list):
        sanitized["reviews"] = [_strip_review(r) for r in reviews]
    return sanitized


def _strip_review(review: dict) -> dict:
    return {k: v for k, v in review.items() if k not in _PII_KEYS}
