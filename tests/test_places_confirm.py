import csv
from pathlib import Path

import pytest

from blackforest_lakes import places
from blackforest_lakes.lakes import LAKE_TARGETS


def _write_candidates(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=places.CANDIDATE_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            full = {k: "" for k in places.CANDIDATE_FIELDNAMES}
            full.update(row)
            writer.writerow(full)


def _base_row(slug: str, place_id: str, selected: str = "") -> dict:
    return {
        "lake_slug": slug,
        "query": "q",
        "rank": 1,
        "display_name": f"{slug} display",
        "formatted_address": "Schwarzwald, Germany",
        "place_id": place_id,
        "primary_type": "natural_feature",
        "lat": "47.9",
        "lng": "8.1",
        "selected": selected,
    }


def test_confirm_mapping_requires_exactly_one_selection_per_lake(tmp_path: Path):
    candidates_path = tmp_path / "candidates.csv"
    output_path = tmp_path / "place_ids.csv"

    rows = [_base_row(t.slug, f"pid_{t.slug}", selected="1") for t in LAKE_TARGETS]
    _write_candidates(candidates_path, rows)

    resolved = places.confirm_mapping(candidates_path, output_path)
    assert len(resolved) == len(LAKE_TARGETS)
    assert all(r.status == "confirmed" for r in resolved)
    assert output_path.exists()


def test_confirm_mapping_marks_unselected_lake_unresolved(tmp_path: Path):
    candidates_path = tmp_path / "candidates.csv"
    output_path = tmp_path / "place_ids.csv"

    rows = [_base_row(t.slug, f"pid_{t.slug}", selected="1") for t in LAKE_TARGETS]
    # Leave the first lake unselected -- e.g. grosser_hohlohsee has no good match.
    rows[0]["selected"] = ""
    _write_candidates(candidates_path, rows)

    resolved = places.confirm_mapping(candidates_path, output_path)
    by_slug = {r.lake_slug: r for r in resolved}
    assert by_slug[LAKE_TARGETS[0].slug].status == "unresolved"
    assert by_slug[LAKE_TARGETS[0].slug].place_id == ""
    assert by_slug[LAKE_TARGETS[1].slug].status == "confirmed"


def test_confirm_mapping_rejects_multiple_selections_for_one_lake(tmp_path: Path):
    candidates_path = tmp_path / "candidates.csv"
    output_path = tmp_path / "place_ids.csv"

    slug = LAKE_TARGETS[0].slug
    rows = [
        _base_row(slug, "pid_a", selected="1"),
        _base_row(slug, "pid_b", selected="yes"),
    ]
    _write_candidates(candidates_path, rows)

    with pytest.raises(ValueError):
        places.confirm_mapping(candidates_path, output_path)
