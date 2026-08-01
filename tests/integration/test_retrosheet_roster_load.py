"""Real DB, real CSV parsing — the network is mocked, returning a small
committed zip (two real, trimmed .ROS files)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from mlb_baseball.connectors import retrosheet_roster as roster

FIXTURE_ZIP = (
    Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet_roster" / "rosters.zip"
)


@pytest.fixture(autouse=True)
def _clean_table(db_conn):
    yield
    with db_conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {roster.TABLE}")
    db_conn.commit()


def test_bootstrap_lands_rows_with_team_and_season_from_filename(db_conn):
    with patch.object(roster, "manifest") as mock_manifest:
        mock_manifest.download_required.return_value = FIXTURE_ZIP
        counts = roster.bootstrap()

    assert counts[roster.TABLE] > 0
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT DISTINCT team_id, _season FROM {roster.TABLE} ORDER BY 1")
        assert cur.fetchall() == [("ANA", "2024"), ("BOS", "2024")]
        cur.execute(f"SELECT player_id, position FROM {roster.TABLE} WHERE team_id = 'ANA' LIMIT 1")
        assert cur.fetchone() is not None


def test_rerunning_replaces_instead_of_duplicating(db_conn):
    with patch.object(roster, "manifest") as mock_manifest:
        mock_manifest.download_required.return_value = FIXTURE_ZIP
        first_counts = roster.bootstrap()
        second_counts = roster.update()

    assert first_counts == second_counts
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {roster.TABLE}")
        (count,) = cur.fetchone()
    assert count == first_counts[roster.TABLE]
