# Black Forest Lake Reviews

Reproducible pipeline: collect Google Maps review text for 14 Black Forest
lakes, translate non-English reviews to English while preserving the
original, and output a tidy CSV for corpus-linguistic analysis (University
of Freiburg, aquatic ecology / environmental education).

Research questions this feeds: how visitors describe these lakes, and how
they respond to recreational restrictions (swimming/boating bans) at
protected sites.

## The 14 target lakes

nonnenmattweiher, feldsee, titisee, schluchsee, windgfaellweiher,
blindensee, glaswaldsee, sankenbachsee, schurmsee, wildsee, wilder_see,
grosser_hohlohsee, mummelsee, herrenwieser_see

See `src/blackforest_lakes/lakes.py` for the exact search queries and the
disambiguation notes baked into Stage 1 (Windgfällweiher spelling, Wildsee
vs. Wilder See, Großer Hohlohsee's weak Maps presence, and the general
"natural feature, not the business named after it" rule). Do not edit that
list without re-running Stage 1 human review.

## Setup

Requires Python 3.11+.

```bash
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"

cp .env.example .env
# fill in .env with your keys (never commit .env -- it's gitignored)
```

### Environment variables

| Variable              | Required | Purpose                                                                 |
|------------------------|----------|--------------------------------------------------------------------------|
| `GOOGLE_MAPS_API_KEY`  | Yes      | Places API (New) -- Text Search (Stage 1) and Place Details (Stage 2). Enable "Places API (New)" in Google Cloud Console. |
| `DEEPL_API_KEY`        | No       | If set, Stage 3 translates with DeepL. |
| `ANTHROPIC_API_KEY`    | Only if `DEEPL_API_KEY` unset | Stage 3 falls back to Anthropic (`claude-sonnet-4-6`) for literal translation. |

## Running the pipeline

The pipeline is three stages. Stage 1 always requires a human in the loop
before anything else runs -- it never auto-selects a place.

### Stage 1 -- resolve place IDs (STOP for human review)

```bash
bfl resolve-places search
```

This runs a Places API (New) Text Search for each of the 14 lakes (biased
to the Black Forest bounding box, roughly 47.6-48.8N / 7.7-8.6E), prints a
candidate table (query, displayName, formattedAddress, place ID,
primaryType, lat/lng, userRatingCount, rating) to the console, and writes
every candidate to `data/place_id_candidates.csv` with a blank `selected`
column.

**Stop here.** Open `data/place_id_candidates.csv`, and for each
`lake_slug` mark exactly one row's `selected` column `1` -- the row that is
the actual natural feature, not a same-named hotel/restaurant/campsite/
parking lot. If no candidate is a plausible match for a lake, leave every
row for it unselected; it will be recorded as unresolved rather than
guessed.

Then:

```bash
bfl resolve-places confirm
```

This reads your edited `data/place_id_candidates.csv` and writes the
confirmed mapping to `data/place_ids.csv` (tracked in git, so the resolved
mapping is reproducible and auditable). Re-running `confirm` after further
edits is safe and overwrites `data/place_ids.csv` in place.

### Stage 2 -- fetch reviews

```bash
bfl fetch-reviews
```

Fetches Place Details (with the `reviews` field) for every `status ==
confirmed` row in `data/place_ids.csv`, via `GooglePlacesProvider`. Raw
responses (with review author PII already stripped -- see below) are
cached to `data/raw/place_details/{place_id}.json`; a rerun without
`--force` never refetches a place it already has.

**Sampling caveat (read before interpreting the corpus):** the Places API
(New) `reviews` field returns **at most 5 reviews per place**, and Google
describes its selection only as "most relevant" -- not random, not
exhaustive, and not documented in detail. In practice this behaves like a
blend of recency and prominence/helpfulness signals. Treat any per-lake
corpus built from this provider as a small, Google-curated, non-random
sample of that place's reviews, not as representative of the full
`userRatingCount` population. `data/coverage_report.csv` documents exactly
how small a fraction this is per lake -- cite it in the methods section
alongside this caveat.

For the full review set instead of this 5-review sample, implement
`PaidProvider` (`src/blackforest_lakes/providers/paid_stub.py`) against a
paid aggregator (Outscraper, SerpApi, Apify, ...). The interface
(`ReviewProvider`, `PlaceReviews`, `RawReview`) is already vendor-neutral;
only `paid_stub.py` needs implementing, per the `TODO` there.

### Stage 3 -- translate and build outputs

```bash
bfl build-output
```

For every fetched review:

1. Detect language on `text_original` with `langdetect` (deterministic,
   seeded) -- the API's `languageCode` is recorded separately as
   `lang_reported` but never trusted on its own.
2. If already English (or the text is empty/undetected), copy it through
   unchanged (`translation_source = "none_already_en"`).
3. Otherwise translate via DeepL if `DEEPL_API_KEY` is set, else Anthropic
   (`claude-sonnet-4-6`) with a prompt for a **literal** translation that
   preserves register, hedging, and complaint intensity -- not a fluent
   idiomatic rewrite, because that's what a linguistic analysis of visitor
   complaints/praise needs intact.
4. Cache the translation by a hash of `text_original` in
   `data/cache/translations.sqlite3`, so reruns never re-translate (and
   never re-charge) text already seen.

If Google's Place Details response includes its own machine translation
(`text` differing from `originalText`), that's captured too during Stage 2
but Stage 3 always runs its own translation regardless, so the translation
source is consistent across the whole corpus. `translation_source`
records which path was actually used per review:
`"deepl" | "anthropic" | "none_already_en" | "google_native"`.
(`"google_native"` is reserved for cases where a future provider ships
only Google's translation with no original -- the current
`GooglePlacesProvider` always has `originalText` and never emits this
value itself.)

Writes:

- `data/blackforest_lake_reviews.csv` -- the corpus, UTF-8 with BOM.
- `data/coverage_report.csv` -- per-lake sampling documentation.

Both are merge-idempotent: rerunning upserts by `review_id`
(`sha256(place_id | publish_time | text_original)[:16]`), so nothing is
ever duplicated and translations already cached are never redone.

### Everything at once

```bash
bfl run-all   # fetch-reviews + build-output; requires place_ids.csv already confirmed
```

`resolve-places` is intentionally excluded from `run-all` -- Stage 1 must
stay a manual, reviewed step.

## Output schema

`data/blackforest_lake_reviews.csv`, one row per review:

| Column                | Description |
|------------------------|-------------|
| `review_id`            | Stable hash of place_id + publish_time + text_original. |
| `lake_slug`             | Canonical lake identifier, e.g. `wilder_see`. |
| `lake_name_de`          | Display name as returned by Google. |
| `place_id`              | Google Places place ID. |
| `lat`, `lng`            | Place coordinates. |
| `lake_total_ratings`    | `userRatingCount` for the place (all-time, not just fetched reviews). |
| `lake_mean_rating`      | `rating` for the place (all-time average). |
| `rating`                | This review's star rating. |
| `text_original`         | Verbatim review text, never modified. |
| `lang_detected`         | `langdetect` output on `text_original`. |
| `lang_reported`         | API-reported `languageCode`, may be null. |
| `text_en`               | English translation, or a copy of `text_original` if already English. |
| `translation_source`    | `deepl` \| `anthropic` \| `none_already_en` \| `google_native`. |
| `publish_time`          | ISO 8601. |
| `relative_time`         | Google's human-readable relative time string. |
| `provider`              | `google_places` \| a paid provider's name, once implemented. |
| `fetched_at`            | ISO 8601, recorded once at first fetch (stable across reruns from cache). |

**Excluded by design, per GDPR:** author name, author profile URL, author
photo URL. These are stripped from the Places API response immediately
after it's received -- before it is cached to `data/raw/` or logged
anywhere (see `src/blackforest_lakes/pii.py`). They never reach any file
in this repository or any intermediate artifact.

`data/coverage_report.csv`: per lake, reviews retrieved vs.
`userRatingCount`, the text-bearing fraction, the language breakdown, and
the publish-time range covered by the retrieved reviews. Use this to
document sampling bias in the methods section.

## Reproducibility & idempotency

- Raw API responses are cached to `data/raw/` as JSON; reruns during
  development never refetch (pass `--force` to bypass).
- Translations are cached by content hash in
  `data/cache/translations.sqlite3`; reruns never re-translate or re-charge.
- The final CSV and coverage report are rebuilt by upserting on
  `review_id`, so reruns never duplicate rows.
- `data/place_ids.csv` (the confirmed Stage 1 mapping) is tracked in git so
  the exact place resolution used for a given corpus is auditable and
  reproducible without repeating the human review step.
- Every HTTP call retries with exponential backoff on `429`/`5xx` and fails
  immediately (no retry) on other `4xx` errors, so auth/config problems
  surface right away instead of being masked by retries.
- Every pipeline run appends a row to `data/request_log.csv` with counts of
  API calls made (Places Text Search, Place Details, DeepL characters,
  Anthropic calls), for tracking billing.

## Project layout

```
src/blackforest_lakes/
  lakes.py              14 target lakes + disambiguation notes + search bias
  places.py              Stage 1: Text Search, candidate table, confirm step
  providers/
    base.py               ReviewProvider interface + PlaceReviews/RawReview schema
    google_places.py       Stage 2 default: Place Details, 5-review cap documented
    paid_stub.py            Stage 2 seam for a paid aggregator (TODO, not implemented)
  fetch.py                Stage 2 orchestration across all confirmed places
  translate.py             Stage 3: langdetect + DeepL/Anthropic translation
  translation_cache.py      sqlite cache keyed by source-text hash
  build_output.py           Final CSV + coverage report, idempotent merge
  pii.py                    Strips author name/profile URL/photo URL (GDPR)
  retry.py                  Exponential backoff for 429/5xx, fail-fast on 4xx
  cache.py, runlog.py, config.py, models.py   shared plumbing
  cli.py                    `bfl` entry point
tests/                      unit tests for hashing, caching, PII-stripping, merge/dedup logic
data/
  place_id_candidates.csv    Stage 1 output, human-annotated (not tracked)
  place_ids.csv               Stage 1 confirmed mapping (tracked)
  raw/                          cached raw API responses (not tracked)
  cache/                         translation cache (not tracked)
  blackforest_lake_reviews.csv    final corpus (not tracked; regenerate via the pipeline)
  coverage_report.csv             sampling documentation (not tracked)
  request_log.csv                 per-run API call counts (not tracked)
```

## Tests

```bash
python -m pytest
```

Covers: PII stripping, translation cache round-tripping, language
detection, translate short-circuit/cache-hit logic, review-id hashing,
idempotent CSV merge, and Stage 1 confirm-step validation (exactly one
selection per lake, unresolved-if-none, error-if-multiple).
