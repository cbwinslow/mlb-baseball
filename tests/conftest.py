"""Shared pytest fixtures for the baseball test suite."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Path fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Return a temporary data directory mirroring the project layout."""
    for subdir in ("raw/mlb", "raw/retrosheet", "raw/statcast", "processed"):
        (tmp_path / subdir).mkdir(parents=True, exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Common result stubs
# ---------------------------------------------------------------------------

@pytest.fixture
def ok_result():
    """A generic success result object."""
    result = MagicMock()
    result.success = True
    result.message = "ok"
    result.records_processed = 10
    result.errors = []
    return result


@pytest.fixture
def error_result():
    """A generic failure result object."""
    result = MagicMock()
    result.success = False
    result.message = "error"
    result.records_processed = 0
    result.errors = ["Something went wrong"]
    return result


# ---------------------------------------------------------------------------
# Season / date helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def season_2024() -> int:
    return 2024


@pytest.fixture
def date_range_2024():
    return {"start_date": "2024-04-01", "end_date": "2024-09-29"}
