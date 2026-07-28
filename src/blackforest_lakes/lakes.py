"""The 14 target lakes and their Stage 1 search parameters.

Disambiguation notes (see task brief — do not change without re-reading the
brief and re-running Stage 1 human review):

- "Windgfaellweiher" -> correct spelling is "Windgfällweiher" (near Schluchsee).
- "Wildsee" and "Wilder See" are two DIFFERENT lakes:
    * Wildsee    -> bog lake at Kaltenbronn.
    * Wilder See -> cirque lake near Ruhestein, in the national park.
  They must resolve to two distinct place_ids / lake_slugs.
- "Grosser Hohlohsee" ("Großer Hohlohsee") is a bog pool at Kaltenbronn and
  may have a weak or absent Google Maps presence -> may resolve as
  unresolved rather than being forced onto a nearby business.
- Several lake names collide with hotels, restaurants, campsites, and
  parking lots named after the lake. Stage 1 must select the natural
  feature (primaryType such as "natural_feature", "park", "tourist_attraction")
  over lodging/food/parking business types, and a human must confirm this
  before Stage 2 fetches anything.

All Text Search queries are biased toward the Black Forest bounding box
below via `locationBias` (Google Places API (New) accepts a rectangle or a
circle; we use a circle centered on the box's midpoint).
"""
from __future__ import annotations

from dataclasses import dataclass

# Roughly 47.6-48.8 N, 7.7-8.6 E (per task brief).
BLACK_FOREST_BOUNDS = {
    "lat_min": 47.6,
    "lat_max": 48.8,
    "lng_min": 7.7,
    "lng_max": 8.6,
}
_BIAS_CENTER = {
    "latitude": (BLACK_FOREST_BOUNDS["lat_min"] + BLACK_FOREST_BOUNDS["lat_max"]) / 2,
    "longitude": (BLACK_FOREST_BOUNDS["lng_min"] + BLACK_FOREST_BOUNDS["lng_max"]) / 2,
}
# Places API (New) Text Search caps locationBias circle radius at 50000m.
# The Black Forest bounding box's diagonal is larger than that, so this is a
# soft bias toward the region's center, not full coverage -- each query's
# text (e.g. "Titisee, Schwarzwald") does the real narrowing.
BIAS_RADIUS_METERS = 50_000.0


@dataclass(frozen=True)
class LakeTarget:
    slug: str
    query: str
    note: str = ""


# lake_slug is the canonical identifier used throughout the pipeline and in
# the final CSV's lake_slug column.
LAKE_TARGETS: list[LakeTarget] = [
    LakeTarget("nonnenmattweiher", "Nonnenmattweiher, Schwarzwald"),
    LakeTarget("feldsee", "Feldsee, Feldberg, Schwarzwald"),
    LakeTarget(
        "titisee",
        "Titisee lake, Hinterzarten, Schwarzwald",
        note="Plain 'Titisee, Schwarzwald' only surfaced the town "
        "(Titisee-Neustadt); this phrasing surfaces the lake itself "
        "(primaryType=lake).",
    ),
    LakeTarget(
        "schluchsee",
        "Schluchsee Stausee, Schwarzwald",
        note="Plain 'Schluchsee, Schwarzwald' returned an untyped locality "
        "result; 'Stausee' (reservoir) surfaces the lake itself "
        "(primaryType=lake).",
    ),
    LakeTarget(
        "windgfaellweiher",
        "Windgfällweiher, Schwarzwald",
        note="Correct spelling is 'Windgfällweiher' (near Schluchsee).",
    ),
    LakeTarget("blindensee", "Blindensee, Schwarzwald"),
    LakeTarget("glaswaldsee", "Glaswaldsee, Schwarzwald"),
    LakeTarget("sankenbachsee", "Sankenbachsee, Schwarzwald"),
    LakeTarget("schurmsee", "Schurmsee, Schwarzwald"),
    LakeTarget(
        "wildsee",
        "Wildsee Kaltenbronn, Schwarzwald",
        note="Bog lake at Kaltenbronn. Distinct from 'Wilder See'.",
    ),
    LakeTarget(
        "wilder_see",
        "Wilder See Ruhestein, Nationalpark Schwarzwald",
        note="Cirque lake near Ruhestein in the national park. Distinct from 'Wildsee'.",
    ),
    LakeTarget(
        "grosser_hohlohsee",
        "Großer Hohlohsee Kaltenbronn, Schwarzwald",
        note="Bog pool at Kaltenbronn; may have weak/no Maps presence -> may resolve unresolved.",
    ),
    LakeTarget("mummelsee", "Mummelsee, Schwarzwald"),
    LakeTarget("herrenwieser_see", "Herrenwieser See, Schwarzwald"),
]

_SLUGS = {t.slug for t in LAKE_TARGETS}
assert len(_SLUGS) == len(LAKE_TARGETS) == 14, "lake slugs must be unique and number 14"


def location_bias_circle() -> dict:
    """Places API (New) Text Search `locationBias.circle` payload."""
    return {"circle": {"center": _BIAS_CENTER, "radius": BIAS_RADIUS_METERS}}
