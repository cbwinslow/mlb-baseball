from unittest.mock import patch

import pytest
import requests

from mlb_baseball.net import get_with_retry


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
