"""Shared retry-on-transient-failure helpers.

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


def call_with_retry(
    fn,
    *args,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    **kwargs,
):
    """Like get_with_retry, but for library calls that make their own internal
    HTTP requests (e.g. the statsapi package) rather than a URL this project
    fetches directly — same transient-failure problem, different call shape.

    Also found the hard way: mlb_api.py's first real historical bootstrap
    (126 seasons, statsapi.mlb.com) hit `requests.exceptions.HTTPError: 503
    Server Error: first byte timeout` on 5 of 126 seasons (2019, 2021-2024) —
    the exact pattern this project's own ADR-007 said to watch for before
    adding retry logic here, not before. Catches requests.exceptions.
    RequestException broadly (covers HTTPError, ConnectionError, Timeout)
    since statsapi's own internal requests.get(...).raise_for_status() can
    surface any of them, not just connection-level failures like
    get_with_retry's narrower ConnectionError.

    A 404 is never retried, regardless of max_attempts — found the hard way
    during mlb_api.py's per-game win-probability/analytics backfill: a game
    with no win-probability data 404s identically every time, so retrying
    it burned the full 3-retry backoff budget (5s+10s+15s = 30s) per game
    for a result that could never change. Across thousands of pre-modern-era
    games with genuinely missing analytics data, this was the dominant cost
    of the whole backfill, not the actual successful API calls. Every other
    RequestException (connection errors, timeouts, 5xx) still gets the full
    retry treatment — only a confirmed HTTP 404 response skips it."""
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except requests.exceptions.RequestException as exc:
            is_404 = (
                isinstance(exc, requests.exceptions.HTTPError)
                and exc.response is not None
                and exc.response.status_code == 404
            )
            if is_404 or attempt == max_attempts:
                raise
            wait = backoff_seconds * attempt
            print(
                f"net: {fn.__name__} failed ({exc}); retrying in {wait:.0f}s "
                f"({attempt}/{max_attempts})"
            )
            time.sleep(wait)
    raise AssertionError("unreachable")  # loop always returns or raises
