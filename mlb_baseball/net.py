"""Shared retry-on-transient-failure helpers.

Found necessary the hard way, not added speculatively: a real bootstrap run
against retrosheet.org failed outright (requests.exceptions.ConnectionError,
"Remote end closed connection without response") after sustained repeated
requests — almost certainly the server rate-limiting or otherwise pushing
back under load. A 128-year bootstrap making 128+ requests needs to survive
one transient failure, not crash the whole run over it.
"""

import logging
import threading
import time

import requests

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BACKOFF_SECONDS = 5.0
RETRYABLE_STATUS_CODES = {408, 425, 429}


def _is_retryable_status(status_code: int | None) -> bool:
    return status_code in RETRYABLE_STATUS_CODES or (status_code is not None and status_code >= 500)


def _retry_delay(
    response: object | None,
    attempt: int,
    backoff_seconds: float,
    *,
    max_retry_after_seconds: float = 300.0,
) -> float:
    """Honor a server's numeric Retry-After response when it is bounded."""
    headers = getattr(response, "headers", {}) or {}
    retry_after = headers.get("Retry-After")
    try:
        if retry_after is not None:
            return min(float(retry_after), max_retry_after_seconds)
    except (TypeError, ValueError):
        pass
    return backoff_seconds * attempt


def _retry_message(
    target: str, exc: Exception | None, wait: float, attempt: int, max_attempts: int
) -> None:
    detail = str(exc) if exc is not None else "retryable HTTP response"
    logger.warning(
        "net: %s failed (%s); retrying in %.0fs (%s/%s)",
        target,
        detail,
        wait,
        attempt,
        max_attempts,
    )


def _request_with_retry(
    method: str,
    url: str,
    *,
    timeout: int,
    max_attempts: int,
    backoff_seconds: float,
    headers: dict[str, str] | None,
) -> requests.Response:
    for attempt in range(1, max_attempts + 1):
        try:
            response = getattr(requests, method)(url, timeout=timeout, headers=headers)
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


def get_with_retry(
    url: str,
    *,
    timeout: int = 60,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    headers: dict[str, str] | None = None,
) -> requests.Response:
    return _request_with_retry(
        "get",
        url,
        timeout=timeout,
        max_attempts=max_attempts,
        backoff_seconds=backoff_seconds,
        headers=headers,
    )


def head_with_retry(
    url: str,
    *,
    timeout: int = 60,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    headers: dict[str, str] | None = None,
) -> requests.Response:
    """get_with_retry for a HEAD request: response headers only, no body."""
    return _request_with_retry(
        "head",
        url,
        timeout=timeout,
        max_attempts=max_attempts,
        backoff_seconds=backoff_seconds,
        headers=headers,
    )


def call_with_retry(
    fn,
    *args,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    max_retry_after_seconds: float = 300.0,
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
            wait = _retry_delay(
                response,
                attempt,
                backoff_seconds,
                max_retry_after_seconds=max_retry_after_seconds,
            )
            _retry_message(fn.__name__, exc, wait, attempt, max_attempts)
            time.sleep(wait)
    raise AssertionError("unreachable")  # loop always returns or raises


class RateLimiter:
    """Thread-safe request pacer shared by every worker of one connector.

    Spaces calls ``1 / rate`` seconds apart across all threads. ``slow_down`` (a 429
    or Retry-After was seen) halves the rate and pauses everyone; ``speed_up`` (called
    after clean responses) climbs back 5% at a time toward the configured ``rate``.
    The ceiling is the source's *documented* limit with a margin, never a guess made
    to be safe: a lower number only costs time."""

    def __init__(self, rate: float, *, min_rate: float = 1.0) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.max_rate = rate
        self.min_rate = min(min_rate, rate)
        self._rate = rate
        self._next = 0.0
        self._lock = threading.Lock()

    @property
    def rate(self) -> float:
        return self._rate

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next)
            self._next = start + 1.0 / self._rate
        wait = start - now
        if wait > 0:
            time.sleep(wait)

    def slow_down(self, pause_seconds: float = 0.0) -> None:
        with self._lock:
            self._rate = max(self.min_rate, self._rate / 2)
            self._next = max(self._next, time.monotonic() + pause_seconds)

    def speed_up(self) -> None:
        with self._lock:
            self._rate = min(self.max_rate, self._rate * 1.05)
