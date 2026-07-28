from blackforest_lakes.pii import strip_review_pii


def test_strip_review_pii_removes_author_attribution():
    payload = {
        "id": "place123",
        "reviews": [
            {
                "rating": 5,
                "text": {"text": "Nice lake", "languageCode": "en"},
                "authorAttribution": {
                    "displayName": "Jane Doe",
                    "uri": "https://maps.google.com/user123",
                    "photoUri": "https://example.com/photo.jpg",
                },
                "publishTime": "2024-01-01T00:00:00Z",
            }
        ],
    }
    sanitized = strip_review_pii(payload)
    assert "authorAttribution" not in sanitized["reviews"][0]
    assert sanitized["reviews"][0]["text"]["text"] == "Nice lake"
    assert sanitized["id"] == "place123"


def test_strip_review_pii_handles_missing_reviews():
    payload = {"id": "place123"}
    sanitized = strip_review_pii(payload)
    assert sanitized == {"id": "place123"}


def test_strip_review_pii_does_not_mutate_input():
    payload = {"reviews": [{"authorAttribution": {"displayName": "X"}, "rating": 1}]}
    strip_review_pii(payload)
    assert "authorAttribution" in payload["reviews"][0]
