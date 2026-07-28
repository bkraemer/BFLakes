from pathlib import Path

import pytest

from blackforest_lakes.cache import RequestCounter
from blackforest_lakes.translate import detect_language, translate_review
from blackforest_lakes.translation_cache import TranslationCache


def test_detect_language_english():
    assert detect_language("This lake was absolutely beautiful and clean.") == "en"


def test_detect_language_german():
    assert detect_language("Dieser See war wunderschön und das Wasser war klar.") == "de"


def test_detect_language_empty_is_undetermined():
    assert detect_language("") == "und"
    assert detect_language("   ") == "und"


def test_translate_review_english_short_circuits(tmp_path: Path):
    cache = TranslationCache(tmp_path / "cache.sqlite3")
    counter = RequestCounter()
    lang, text_en, source = translate_review(
        "A beautiful lake, would visit again.",
        cache=cache,
        counter=counter,
        deepl_api_key=None,
        anthropic_api_key=None,
    )
    assert lang == "en"
    assert text_en == "A beautiful lake, would visit again."
    assert source == "none_already_en"
    assert counter.as_dict() == {}


def test_translate_review_uses_cache_without_calling_provider(tmp_path: Path):
    cache = TranslationCache(tmp_path / "cache.sqlite3")
    german_text = "Dieser See war wunderschön und das Wasser war klar."
    cache.put(german_text, "This lake was beautiful and the water was clear.", "deepl")
    counter = RequestCounter()

    lang, text_en, source = translate_review(
        german_text,
        cache=cache,
        counter=counter,
        deepl_api_key=None,
        anthropic_api_key=None,
    )
    assert lang == "de"
    assert text_en == "This lake was beautiful and the water was clear."
    assert source == "deepl"
    # No API keys were configured, yet this succeeded -- proof the cache hit
    # short-circuited before any provider call was attempted.
    assert counter.as_dict() == {}


def test_translate_review_raises_without_any_key_on_cache_miss(tmp_path: Path):
    cache = TranslationCache(tmp_path / "cache.sqlite3")
    counter = RequestCounter()
    with pytest.raises(RuntimeError):
        translate_review(
            "Dieser See war wunderschön.",
            cache=cache,
            counter=counter,
            deepl_api_key=None,
            anthropic_api_key=None,
        )
