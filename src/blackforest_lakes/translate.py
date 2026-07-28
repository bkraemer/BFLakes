"""Stage 3: language detection + translation to English.

Language detection uses langdetect rather than trusting the Places API's
`languageCode` alone (that field is reviewer-self-reported / Google-inferred
at review-submission time and is frequently wrong or missing for short
text -- see task brief).

Translation: DeepL if DEEPL_API_KEY is set, else the Anthropic API
(claude-sonnet-4-6) with a prompt for a literal translation that preserves
register, hedging, and complaint intensity -- we explicitly do NOT want a
fluent idiomatic rewrite, because register and hedging are exactly what a
corpus-linguistic analysis of visitor complaints/praise needs to keep.

Results are cached by translation_cache.TranslationCache, keyed by a hash
of the source text, so reruns never re-translate and never re-charge.
"""
from __future__ import annotations

import logging

from langdetect import DetectorFactory, LangDetectException, detect

from .cache import RequestCounter
from .retry import ApiAuthError, call_with_retry
from .translation_cache import TranslationCache

logger = logging.getLogger("blackforest_lakes")

# Deterministic language detection (langdetect is otherwise seeded from
# wall-clock time and can flip results between runs on ambiguous text).
DetectorFactory.seed = 0

ANTHROPIC_MODEL = "claude-sonnet-4-6"

LITERAL_TRANSLATION_SYSTEM_PROMPT = """\
You are a literal translator for a corpus-linguistics research project on \
visitor reviews of lakes in the Black Forest, Germany. Translate the \
review text into English as literally as possible while staying \
grammatical:

- Preserve register (formal/informal), hedging ("vielleicht", "etwas", \
"a bit"), and complaint or praise intensity exactly -- do not soften, \
strengthen, or smooth them into idiomatic English.
- Do not summarize, paraphrase, add, or drop content.
- Preserve sentence boundaries and paragraph breaks where possible.
- Output ONLY the translation, with no preamble, quotation marks, or \
commentary.\
"""


def detect_language(text: str) -> str:
    """Returns an ISO 639-1-ish code, or 'und' (undetermined) for empty/too-short text."""
    stripped = text.strip()
    if not stripped:
        return "und"
    try:
        return detect(stripped)
    except LangDetectException:
        return "und"


def _translate_with_deepl(text: str, api_key: str, counter: RequestCounter) -> str:
    import deepl

    translator = deepl.Translator(api_key)

    def _call() -> str:
        result = translator.translate_text(text, target_lang="EN-US")
        return result.text

    def _is_auth_error(e: Exception) -> bool:
        return isinstance(e, deepl.exceptions.AuthorizationException)

    def _is_retryable(e: Exception) -> bool:
        return isinstance(
            e,
            (deepl.exceptions.TooManyRequestsException, deepl.exceptions.ConnectionException),
        )

    translated = call_with_retry(_call, is_retryable=_is_retryable, is_auth_error=_is_auth_error)
    counter.add("deepl_chars", len(text))
    return translated


def _translate_with_anthropic(text: str, api_key: str, counter: RequestCounter) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    def _call() -> str:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2048,
            system=LITERAL_TRANSLATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        return "".join(block.text for block in response.content if block.type == "text").strip()

    def _is_auth_error(e: Exception) -> bool:
        return isinstance(e, anthropic.AuthenticationError)

    def _is_retryable(e: Exception) -> bool:
        if isinstance(e, anthropic.RateLimitError):
            return True
        if isinstance(e, anthropic.APIStatusError):
            return e.status_code >= 500
        return False

    translated = call_with_retry(_call, is_retryable=_is_retryable, is_auth_error=_is_auth_error)
    counter.add("anthropic_translate_calls")
    return translated


def translate_review(
    text_original: str,
    *,
    cache: TranslationCache,
    counter: RequestCounter,
    deepl_api_key: str | None,
    anthropic_api_key: str | None,
) -> tuple[str, str, str]:
    """Returns (lang_detected, text_en, translation_source).

    text_original must not be mutated or overwritten -- caller keeps it in a
    separate CSV column.
    """
    lang_detected = detect_language(text_original)

    if lang_detected in ("en", "und") or not text_original.strip():
        return lang_detected, text_original, "none_already_en"

    cached = cache.get(text_original)
    if cached is not None:
        translated_text, translation_source = cached
        return lang_detected, translated_text, translation_source

    if deepl_api_key:
        try:
            translated = _translate_with_deepl(text_original, deepl_api_key, counter)
            source = "deepl"
        except ApiAuthError:
            raise
    elif anthropic_api_key:
        translated = _translate_with_anthropic(text_original, anthropic_api_key, counter)
        source = "anthropic"
    else:
        raise RuntimeError(
            "Neither DEEPL_API_KEY nor ANTHROPIC_API_KEY is set; cannot translate "
            f"non-English text (detected lang={lang_detected})."
        )

    cache.put(text_original, translated, source)
    return lang_detected, translated, source
