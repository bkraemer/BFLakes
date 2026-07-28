"""Exponential backoff for transient HTTP failures.

Retries on 429 (rate limit) and 5xx (server error). Fails loudly and
immediately on 4xx auth/client errors (e.g. 400/401/403/404) since retrying
those just burns quota without fixing anything.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

import requests

logger = logging.getLogger("blackforest_lakes")

T = TypeVar("T")

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class ApiAuthError(RuntimeError):
    """Raised immediately (no retry) on a 4xx that isn't 429."""


def request_with_retry(
    method: str,
    url: str,
    *,
    max_attempts: int = 5,
    base_delay_seconds: float = 1.0,
    **kwargs,
) -> requests.Response:
    """requests.request wrapped with retry-on-429/5xx, fail-fast-on-4xx."""
    attempt = 0
    while True:
        attempt += 1
        response = requests.request(method, url, **kwargs)
        if response.status_code < 400:
            return response

        if response.status_code in RETRYABLE_STATUS_CODES and attempt < max_attempts:
            delay = base_delay_seconds * (2 ** (attempt - 1))
            logger.warning(
                "HTTP %s from %s (attempt %d/%d) -- retrying in %.1fs",
                response.status_code,
                url,
                attempt,
                max_attempts,
                delay,
            )
            time.sleep(delay)
            continue

        if response.status_code in RETRYABLE_STATUS_CODES:
            response.raise_for_status()

        # Non-retryable 4xx: fail loudly, immediately.
        raise ApiAuthError(
            f"HTTP {response.status_code} from {url}: {response.text[:500]}"
        )


def call_with_retry(
    func: Callable[[], T],
    *,
    is_retryable: Callable[[Exception], bool],
    is_auth_error: Callable[[Exception], bool],
    max_attempts: int = 5,
    base_delay_seconds: float = 1.0,
) -> T:
    """Retry wrapper for SDK calls (DeepL, Anthropic) that don't go through requests."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return func()
        except Exception as e:  # noqa: BLE001 -- classified by caller-supplied predicates
            if is_auth_error(e):
                raise ApiAuthError(str(e)) from e
            if is_retryable(e) and attempt < max_attempts:
                delay = base_delay_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "%s (attempt %d/%d) -- retrying in %.1fs",
                    e,
                    attempt,
                    max_attempts,
                    delay,
                )
                time.sleep(delay)
                continue
            raise
