from pathlib import Path

from blackforest_lakes.translation_cache import TranslationCache, text_hash


def test_text_hash_is_stable_and_content_dependent():
    assert text_hash("hello") == text_hash("hello")
    assert text_hash("hello") != text_hash("hello!")


def test_cache_roundtrip(tmp_path: Path):
    with TranslationCache(tmp_path / "cache.sqlite3") as cache:
        assert cache.get("Schöner See") is None
        cache.put("Schöner See", "Beautiful lake", "deepl")
        assert cache.get("Schöner See") == ("Beautiful lake", "deepl")


def test_cache_persists_across_instances(tmp_path: Path):
    db_path = tmp_path / "cache.sqlite3"
    with TranslationCache(db_path) as cache:
        cache.put("Wasser ist kalt", "Water is cold", "anthropic")
    with TranslationCache(db_path) as cache2:
        assert cache2.get("Wasser ist kalt") == ("Water is cold", "anthropic")
