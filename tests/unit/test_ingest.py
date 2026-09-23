"""Pure unit coverage for mlb_baseball.ingest -- no database needed."""

import pytest

from mlb_baseball.ingest import _resolve_workflow_lock_timeout_seconds


def test_default_is_thirty_seconds_when_unset(monkeypatch):
    monkeypatch.delenv("MLB_WORKFLOW_LOCK_TIMEOUT_SECONDS", raising=False)
    assert _resolve_workflow_lock_timeout_seconds() == 30.0


def test_a_valid_override_is_used(monkeypatch):
    monkeypatch.setenv("MLB_WORKFLOW_LOCK_TIMEOUT_SECONDS", "5.5")
    assert _resolve_workflow_lock_timeout_seconds() == 5.5


@pytest.mark.parametrize(
    "raw",
    [
        "not-a-number",
        "0",
        "-1",
        "inf",
        "-inf",
        "nan",
        "",
    ],
)
def test_a_garbled_or_non_positive_override_falls_back_to_the_default(monkeypatch, raw):
    """A typo, an inf/nan, or a non-positive value must not crash this
    widely-imported module at import time, and must not silently produce a
    'lock_timeout = 0ms' -- which PostgreSQL treats as "wait forever", the
    opposite of a bounded wait."""
    monkeypatch.setenv("MLB_WORKFLOW_LOCK_TIMEOUT_SECONDS", raw)
    assert _resolve_workflow_lock_timeout_seconds() == 30.0
