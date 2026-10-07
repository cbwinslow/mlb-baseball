"""A per-team reference call that the source answers with 404 is an empty answer."""

import pytest
import requests

from mlb_baseball.connectors import mlb_api


def _http_error(status: int) -> requests.exceptions.HTTPError:
    response = requests.Response()
    response.status_code = status
    return requests.exceptions.HTTPError(f"{status} error", response=response)


def test_a_404_for_one_team_is_an_empty_answer(monkeypatch):
    def fake(fn, endpoint, params):
        raise _http_error(404)

    monkeypatch.setattr(mlb_api, "call_with_retry", fake)

    assert mlb_api._fetch_reference_task((114, "team_leaders", {"season": 2023})) == (114, {})


def test_any_other_error_still_raises(monkeypatch):
    def fake(fn, endpoint, params):
        raise _http_error(500)

    monkeypatch.setattr(mlb_api, "call_with_retry", fake)

    with pytest.raises(requests.exceptions.HTTPError):
        mlb_api._fetch_reference_task((114, "team_leaders", {"season": 2023}))
