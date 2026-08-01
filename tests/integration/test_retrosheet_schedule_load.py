"""Real DB, real CSV parsing — the network is mocked, returning a small
committed zip (a synthetic 1877schedule.csv matching the real header shape,
including the duplicate League/Game columns)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from mlb_baseball.connectors import retrosheet_schedule as schedule

FIXTURE_ZIP = (
    Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet_schedule" / "schedule.zip"
)


@pytest.fixture(autouse=True)
def _clean_table(db_conn):
    yield
    with db_conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {schedule.TABLE}")
    db_conn.commit()


def test_bootstrap_lands_rows_with_disambiguated_league_game_columns(db_conn):
    with patch.object(schedule, "manifest") as mock_manifest:
        mock_manifest.download_required.return_value = FIXTURE_ZIP
        counts = schedule.bootstrap()

    assert counts[schedule.TABLE] == 2
    with db_conn.cursor() as cur:
        cur.execute(
            f"SELECT visitor, visitor_league, home, home_league, _season "
            f"FROM {schedule.TABLE} ORDER BY date LIMIT 1"
        )
        row = cur.fetchone()
    assert row == ("BSN", "NL", "HAR", "NL", "1877")


def test_rerunning_replaces_instead_of_duplicating(db_conn):
    with patch.object(schedule, "manifest") as mock_manifest:
        mock_manifest.download_required.return_value = FIXTURE_ZIP
        first_counts = schedule.bootstrap()
        second_counts = schedule.update()

    assert first_counts == second_counts
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {schedule.TABLE}")
        (count,) = cur.fetchone()
    assert count == first_counts[schedule.TABLE]
