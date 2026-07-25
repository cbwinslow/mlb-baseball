from pathlib import Path

import pytest

from mlb_baseball import chadwick_tools

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet_event"


def test_run_cwevent_parses_plays_with_full_field_set():
    df = chadwick_tools.run_cwevent(FIXTURE_DIR, 2024)

    assert len(df) > 0
    assert {"GAME_ID", "BAT_ID", "PIT_ID", "EVENT_TX"} <= set(df.columns)
    assert set(df["GAME_ID"]) == {"ANA202404050", "ANA202404060"}


def test_run_cwgame_parses_one_row_per_game():
    df = chadwick_tools.run_cwgame(FIXTURE_DIR, 2024)

    assert set(df["GAME_ID"]) == {"ANA202404050", "ANA202404060"}
    assert {"HOME_TEAM_ID", "AWAY_TEAM_ID", "ATTEND_PARK_CT"} <= set(df.columns)


def test_run_cwevent_raises_on_directory_with_no_event_files(tmp_path):
    with pytest.raises(RuntimeError, match="no event files"):
        chadwick_tools.run_cwevent(tmp_path, 2024)


def test_run_cwgame_raises_on_directory_with_no_event_files(tmp_path):
    with pytest.raises(RuntimeError, match="no event files"):
        chadwick_tools.run_cwgame(tmp_path, 2024)
