"""Command-line entry point: `bfl <subcommand>`."""
from __future__ import annotations

import argparse
import logging
import sys

from . import build_output, config, fetch, places, runlog
from .cache import RequestCounter
from .providers.google_places import GooglePlacesProvider
from .translation_cache import TranslationCache


def cmd_resolve_places_search(args: argparse.Namespace) -> int:
    logger = runlog.setup_logging("resolve_places_search")
    api_key = config.google_maps_api_key(required=True)
    counter = RequestCounter()

    candidates = places.search_all_lakes(api_key, counter, force=args.force)
    places.print_candidate_table(candidates)
    places.write_candidates_csv(candidates)

    counter.log_summary()
    runlog.append_request_log("resolve_places_search", counter.as_dict())

    print()
    print("=" * 78)
    print("STOP: Stage 1 requires human review before anything is fetched.")
    print(f"Review the table above (and {config.PLACE_ID_CANDIDATES_CSV}).")
    print(
        "For each lake, set the `selected` column to 1 on the ONE row that is "
        "the natural feature (not a hotel/restaurant/campsite/parking lot named "
        "after it). Leave a lake with no good match entirely unselected -- it "
        "will be recorded as unresolved rather than guessed."
    )
    print("Then run: bfl resolve-places confirm")
    print("=" * 78)
    logger.info("Stage 1 search complete: %d candidates across all lakes.", len(candidates))
    return 0


def cmd_resolve_places_confirm(args: argparse.Namespace) -> int:
    logger = runlog.setup_logging("resolve_places_confirm")
    resolved = places.confirm_mapping()
    n_confirmed = sum(1 for r in resolved if r.status == "confirmed")
    n_unresolved = len(resolved) - n_confirmed
    print(f"Confirmed {n_confirmed}/{len(resolved)} lakes; {n_unresolved} unresolved.")
    print(f"Wrote {config.PLACE_IDS_CSV}. Review it, then run: bfl fetch-reviews")
    logger.info("Stage 1 confirmed: %d confirmed, %d unresolved.", n_confirmed, n_unresolved)
    return 0


def cmd_fetch_reviews(args: argparse.Namespace) -> int:
    logger = runlog.setup_logging("fetch_reviews")
    api_key = config.google_maps_api_key(required=True)
    counter = RequestCounter()

    resolved_places = places.load_confirmed_places()
    provider = GooglePlacesProvider(api_key, counter=counter)
    place_reviews = fetch.fetch_all_places(resolved_places, provider, force=args.force)

    total_reviews = sum(len(pr.reviews) for pr in place_reviews.values())
    logger.info(
        "Fetched %d places, %d reviews total (Google Places API caps this at "
        "5 'most relevant' reviews per place -- see providers/google_places.py).",
        len(place_reviews),
        total_reviews,
    )
    counter.log_summary()
    runlog.append_request_log("fetch_reviews", counter.as_dict())
    return 0


def cmd_build_output(args: argparse.Namespace) -> int:
    logger = runlog.setup_logging("build_output")
    counter = RequestCounter()

    resolved_places = places.load_confirmed_places()
    # Reuses cached raw Place Details from `fetch-reviews` when present; only
    # calls the Places API for places that were never fetched.
    provider = GooglePlacesProvider(config.google_maps_api_key(required=True), counter=counter)
    place_reviews = fetch.fetch_all_places(resolved_places, provider, force=False)

    deepl_key = config.deepl_api_key()
    anthropic_key = config.anthropic_api_key(required=not deepl_key)
    if deepl_key:
        logger.info("Translation backend: DeepL")
    else:
        logger.info("Translation backend: Anthropic (%s) -- DEEPL_API_KEY not set", "claude-sonnet-4-6")

    with TranslationCache(config.TRANSLATION_CACHE_DB) as cache:
        new_rows = build_output.build_rows(
            resolved_places,
            place_reviews,
            translation_cache=cache,
            counter=counter,
            deepl_api_key=deepl_key,
            anthropic_api_key=anthropic_key,
        )

    existing_rows = build_output.read_existing_csv(config.OUTPUT_CSV)
    merged_rows = build_output.merge_rows(existing_rows, new_rows)
    build_output.write_output_csv(merged_rows)
    build_output.write_coverage_report(resolved_places, place_reviews, merged_rows)

    counter.log_summary()
    runlog.append_request_log("build_output", counter.as_dict())
    return 0


def cmd_run_all(args: argparse.Namespace) -> int:
    rc = cmd_fetch_reviews(args)
    if rc != 0:
        return rc
    return cmd_build_output(args)


def main(argv: list[str] | None = None) -> int:
    config.ensure_data_dirs()
    parser = argparse.ArgumentParser(prog="bfl", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_resolve = sub.add_parser("resolve-places", help="Stage 1: resolve lake names to place_ids")
    resolve_sub = p_resolve.add_subparsers(dest="resolve_command", required=True)

    p_search = resolve_sub.add_parser("search", help="Text Search every lake, print/write candidates")
    p_search.add_argument("--force", action="store_true", help="bypass the raw response cache")
    p_search.set_defaults(func=cmd_resolve_places_search)

    p_confirm = resolve_sub.add_parser(
        "confirm", help="turn the human-annotated candidates CSV into data/place_ids.csv"
    )
    p_confirm.set_defaults(func=cmd_resolve_places_confirm)

    p_fetch = sub.add_parser("fetch-reviews", help="Stage 2: fetch reviews for confirmed places")
    p_fetch.add_argument("--force", action="store_true", help="bypass the raw response cache")
    p_fetch.set_defaults(func=cmd_fetch_reviews)

    p_build = sub.add_parser(
        "build-output", help="Stage 3: translate + write the final CSV and coverage report"
    )
    p_build.set_defaults(func=cmd_build_output)

    p_run_all = sub.add_parser(
        "run-all", help="fetch-reviews + build-output (requires data/place_ids.csv already confirmed)"
    )
    p_run_all.add_argument("--force", action="store_true", help="bypass the raw response cache")
    p_run_all.set_defaults(func=cmd_run_all)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as e:
        logging.getLogger("blackforest_lakes").error("%s: %s", type(e).__name__, e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
