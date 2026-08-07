import pandas as pd
import pytest

from mlb_baseball.load import _pg_column_names


def test_rejects_source_column_names_that_sanitize_to_empty():
    with pytest.raises(ValueError, match="sanitizes to empty"):
        _pg_column_names(pd.DataFrame({"---": [1]}))


def test_rejects_source_column_names_that_collide_after_sanitization():
    with pytest.raises(ValueError, match="collide"):
        _pg_column_names(pd.DataFrame({"player-id": [1], "player id": [2]}))
