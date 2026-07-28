from blackforest_lakes.build_output import make_review_id, merge_rows


def test_make_review_id_is_stable():
    a = make_review_id("place1", "2024-01-01T00:00:00Z", "Nice lake")
    b = make_review_id("place1", "2024-01-01T00:00:00Z", "Nice lake")
    assert a == b


def test_make_review_id_differs_on_any_input_change():
    base = make_review_id("place1", "2024-01-01T00:00:00Z", "Nice lake")
    assert base != make_review_id("place2", "2024-01-01T00:00:00Z", "Nice lake")
    assert base != make_review_id("place1", "2024-01-02T00:00:00Z", "Nice lake")
    assert base != make_review_id("place1", "2024-01-01T00:00:00Z", "Nice lake!")


def test_merge_rows_upserts_by_review_id_without_duplicating():
    existing = [
        {"review_id": "r1", "lake_slug": "titisee", "publish_time": "2024-01-01", "rating": 4},
        {"review_id": "r2", "lake_slug": "titisee", "publish_time": "2024-01-02", "rating": 5},
    ]
    new = [
        {"review_id": "r1", "lake_slug": "titisee", "publish_time": "2024-01-01", "rating": 3},
        {"review_id": "r3", "lake_slug": "titisee", "publish_time": "2024-01-03", "rating": 2},
    ]
    merged = merge_rows(existing, new)
    assert len(merged) == 3
    by_id = {r["review_id"]: r for r in merged}
    assert by_id["r1"]["rating"] == 3  # overwritten, not duplicated
    assert by_id["r2"]["rating"] == 5  # untouched
    assert by_id["r3"]["rating"] == 2  # appended


def test_merge_rows_is_idempotent_on_rerun_with_identical_input():
    rows = [{"review_id": "r1", "lake_slug": "feldsee", "publish_time": "2024-01-01", "rating": 4}]
    once = merge_rows([], rows)
    twice = merge_rows(once, rows)
    assert once == twice
