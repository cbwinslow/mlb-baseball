"""Shared HTTP fetch helper with retry-on-transient-failure.

Found necessary the hard way, not added speculatively: a real bootstrap run
against retrosheet.org failed outright (requests.exceptions.ConnectionError,
"Remote end closed connection without response") after sustained repeated
requests — almost certainly the server rate-limiting or otherwise pushing
back under load. A 128-year bootstrap making 128+ requests needs to survive
one transient failure, not crash the whole run over it.
"""

import time

import requests

DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BACKOFF_SECONDS = 5.0


def get_with_retry(
    url: str,
    *,
    timeout: int = 60,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
) -> requests.Response:
    for attempt in range(1, max_attempts + 1):
        try:
            return requests.get(url, timeout=timeout)
        except requests.exceptions.ConnectionError as exc:
            if attempt == max_attempts:
                raise
            wait = backoff_seconds * attempt
            print(f"net: {url} failed ({exc}); retrying in {wait:.0f}s ({attempt}/{max_attempts})")
            time.sleep(wait)
    raise AssertionError("unreachable")  # loop always returns or raises
