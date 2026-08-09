from unittest.mock import Mock, patch

import pytest
import requests

from mlb_baseball.net import call_with_retry, get_with_retry


def test_returns_response_on_first_success():
    fake_response = object()
    with patch("mlb_baseball.net.requests.get", return_value=fake_response) as mock_get:
        result = get_with_retry("https://example.com/x", max_attempts=3, backoff_seconds=0)

    assert result is fake_response
    mock_get.assert_called_once()


def test_retries_after_connection_error_then_succeeds():
    fake_response = object()
    with patch(
        "mlb_baseball.net.requests.get",
        side_effect=[requests.exceptions.ConnectionError("boom"), fake_response],
    ) as mock_get:
        result = get_with_retry("https://example.com/x", max_attempts=3, backoff_seconds=0)

    assert result is fake_response
    assert mock_get.call_count == 2


def test_raises_after_exhausting_all_attempts():
    with patch(
        "mlb_baseball.net.requests.get",
        side_effect=requests.exceptions.ConnectionError("boom"),
    ) as mock_get:
        with pytest.raises(requests.exceptions.ConnectionError):
            get_with_retry("https://example.com/x", max_attempts=3, backoff_seconds=0)

    assert mock_get.call_count == 3


def test_retries_retryable_http_response_and_honors_retry_after():
    rate_limited = Mock(status_code=429, headers={"Retry-After": "2"})
    success = Mock(status_code=200)
    with (
        patch("mlb_baseball.net.requests.get", side_effect=[rate_limited, success]) as mock_get,
        patch("mlb_baseball.net.time.sleep") as sleep,
    ):
        result = get_with_retry("https://example.com/x", max_attempts=3, backoff_seconds=0)

    assert result is success
    assert mock_get.call_count == 2
    sleep.assert_called_once_with(2.0)


def test_returns_non_retryable_http_response_without_retrying():
    missing = Mock(status_code=404)
    with patch("mlb_baseball.net.requests.get", return_value=missing) as mock_get:
        result = get_with_retry("https://example.com/x", max_attempts=3, backoff_seconds=0)

    assert result is missing
    mock_get.assert_called_once()


def test_call_with_retry_returns_result_on_first_success():
    fn = lambda **kwargs: {"ok": True, "kwargs": kwargs}  # noqa: E731
    result = call_with_retry(fn, season=2026, max_attempts=3, backoff_seconds=0)

    assert result == {"ok": True, "kwargs": {"season": 2026}}


def test_call_with_retry_retries_after_http_error_then_succeeds():
    # Real failure this was added for: statsapi's own internal requests.get()
    # surfaced "503 Server Error: first byte timeout" on 5/126 seasons during
    # the first real mlb_api historical bootstrap.
    calls = {"count": 0}

    def flaky(**kwargs):
        calls["count"] += 1
        if calls["count"] < 2:
            raise requests.exceptions.HTTPError("503 Server Error: first byte timeout")
        return "success"

    result = call_with_retry(flaky, season=2019, max_attempts=3, backoff_seconds=0)

    assert result == "success"
    assert calls["count"] == 2


def test_call_with_retry_raises_after_exhausting_all_attempts():
    def always_fails(**kwargs):
        raise requests.exceptions.HTTPError("503 Server Error")

    with pytest.raises(requests.exceptions.HTTPError):
        call_with_retry(always_fails, max_attempts=3, backoff_seconds=0)


def test_call_with_retry_does_not_retry_a_404():
    # Regression: a 404 means the resource genuinely doesn't exist (e.g. a
    # game with no win-probability data) and will 404 identically on every
    # retry — burning the full backoff budget on it is pure waste. Found for
    # real during mlb_api.py's per-game analytics backfill: thousands of
    # pre-modern-era games hitting the full 3-retry cycle (30s each) for a
    # result that could never change.
    calls = {"count": 0}
    fake_response = type("FakeResponse", (), {"status_code": 404})()

    def always_404(**kwargs):
        calls["count"] += 1
        raise requests.exceptions.HTTPError("404 Client Error: Not Found", response=fake_response)

    with pytest.raises(requests.exceptions.HTTPError):
        call_with_retry(always_404, max_attempts=3, backoff_seconds=0)

    assert calls["count"] == 1  # no retries — one call, then raise immediately


def test_call_with_retry_does_not_retry_other_non_transient_4xx_errors():
    calls = {"count": 0}
    fake_response = type("FakeResponse", (), {"status_code": 400})()

    def always_bad_request(**kwargs):
        calls["count"] += 1
        raise requests.exceptions.HTTPError("400 Client Error", response=fake_response)

    with pytest.raises(requests.exceptions.HTTPError):
        call_with_retry(always_bad_request, max_attempts=3, backoff_seconds=0)

    assert calls["count"] == 1


def test_call_with_retry_still_retries_a_503_after_this_change():
    # A confirmed 404 skips retries, but every other HTTP error (including
    # one with a real response object attached, unlike the other retry
    # tests above which use a bare HTTPError with no response) still gets
    # the full retry treatment.
    calls = {"count": 0}
    fake_response = type("FakeResponse", (), {"status_code": 503})()

    def flaky(**kwargs):
        calls["count"] += 1
        if calls["count"] < 2:
            raise requests.exceptions.HTTPError("503 Server Error", response=fake_response)
        return "success"

    result = call_with_retry(flaky, max_attempts=3, backoff_seconds=0)

    assert result == "success"
    assert calls["count"] == 2


def test_call_with_retry_can_cap_retry_after_for_bounded_parallel_work():
    calls = {"count": 0}
    fake_response = type(
        "FakeResponse", (), {"status_code": 503, "headers": {"Retry-After": "300"}}
    )()

    def flaky(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise requests.exceptions.HTTPError("503 Server Error", response=fake_response)
        return "success"

    with patch("mlb_baseball.net.time.sleep") as sleep:
        result = call_with_retry(
            flaky,
            max_attempts=3,
            backoff_seconds=0,
            max_retry_after_seconds=15,
        )

    assert result == "success"
    sleep.assert_called_once_with(15)


def test_call_with_retry_does_not_catch_unrelated_exceptions():
    # Only network-shaped failures are worth retrying — a bug in the
    # connector's own code (e.g. a KeyError from unexpected response shape)
    # should surface immediately, not be silently retried 3 times first.
    def broken(**kwargs):
        raise ValueError("not a network problem")

    with pytest.raises(ValueError):
        call_with_retry(broken, max_attempts=3, backoff_seconds=0)
