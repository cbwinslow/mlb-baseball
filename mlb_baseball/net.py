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
RETRYABLE_STATUS_CODES = {408, 425, 429}


def _is_retryable_status(status_code: int | None) -> bool:
    return status_code in RETRYABLE_STATUS_CODES or (status_code is not None and status_code >= 500)


def _retry_delay(response: object | None, attempt: int, backoff_seconds: float) -> float:
    """Honor a server's numeric Retry-After response when it is bounded."""
    headers = getattr(response, "headers", {}) or {}
    retry_after = headers.get("Retry-After")
    try:
        if retry_after is not None:
            return min(float(retry_after), 300.0)
    except (TypeError, ValueError):
        pass
    return backoff_seconds * attempt


def _retry_message(
    target: str, exc: Exception | None, wait: float, attempt: int, max_attempts: int
) -> None:
    detail = str(exc) if exc is not None else "retryable HTTP response"
    print(f"net: {target} failed ({detail}); retrying in {wait:.0f}s ({attempt}/{max_attempts})")


def get_with_retry(
    url: str,
    *,
    timeout: int = 60,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    headers: dict[str, str] | None = None,
) -> requests.Response:
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(url, timeout=timeout, headers=headers)
        except requests.exceptions.RequestException as exc:
            if attempt == max_attempts:
                raise
            wait = _retry_delay(getattr(exc, "response", None), attempt, backoff_seconds)
            _retry_message(url, exc, wait, attempt, max_attempts)
            time.sleep(wait)
            continue
        status_code = getattr(response, "status_code", None)
        if not _is_retryable_status(status_code) or attempt == max_attempts:
            return response
        wait = _retry_delay(response, attempt, backoff_seconds)
        _retry_message(url, None, wait, attempt, max_attempts)
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

    Confirmed non-transient 4xx responses are never retried, regardless of
    max_attempts — found the hard way
    during mlb_api.py's per-game win-probability/analytics backfill: a game
    with no win-probability data 404s identically every time, so retrying
    it burned the full 3-retry backoff budget (5s+10s+15s = 30s) per game
    for a result that could never change. Across thousands of pre-modern-era
    games with genuinely missing analytics data, this was the dominant cost
    of the whole backfill, not the actual successful API calls. Every other
    RequestException (connection errors, timeouts, 5xx) still gets the full
    retry treatment — only confirmed transient HTTP statuses (408, 425, 429,
    and 5xx) get another attempt."""
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except requests.exceptions.RequestException as exc:
            response = exc.response if isinstance(exc, requests.exceptions.HTTPError) else None
            status_code = getattr(response, "status_code", None)
            if (
                status_code is not None and not _is_retryable_status(status_code)
            ) or attempt == max_attempts:
                raise
            wait = _retry_delay(response, attempt, backoff_seconds)
            _retry_message(fn.__name__, exc, wait, attempt, max_attempts)
            time.sleep(wait)
    raise AssertionError("unreachable")  # loop always returns or raises
