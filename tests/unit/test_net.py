from unittest.mock import patch

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


def test_call_with_retry_does_not_catch_unrelated_exceptions():
    # Only network-shaped failures are worth retrying — a bug in the
    # connector's own code (e.g. a KeyError from unexpected response shape)
    # should surface immediately, not be silently retried 3 times first.
    def broken(**kwargs):
        raise ValueError("not a network problem")

    with pytest.raises(ValueError):
        call_with_retry(broken, max_attempts=3, backoff_seconds=0)
