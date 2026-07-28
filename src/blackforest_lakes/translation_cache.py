"""Persistent translation cache, keyed by a hash of the source text.

Reruns never re-translate text already seen, regardless of which review or
place it came from -- so a duplicated review blurb across lakes only costs
one translation call, and reruns during development are free.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TranslationCache:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS translations (
                text_hash TEXT PRIMARY KEY,
                translated_text TEXT NOT NULL,
                translation_source TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, source_text: str) -> tuple[str, str] | None:
        """Returns (translated_text, translation_source) or None on a cache miss."""
        row = self._conn.execute(
            "SELECT translated_text, translation_source FROM translations WHERE text_hash = ?",
            (text_hash(source_text),),
        ).fetchone()
        return tuple(row) if row else None

    def put(self, source_text: str, translated_text: str, translation_source: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO translations (text_hash, translated_text, "
            "translation_source, created_at) VALUES (?, ?, ?, ?)",
            (
                text_hash(source_text),
                translated_text,
                translation_source,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "TranslationCache":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
