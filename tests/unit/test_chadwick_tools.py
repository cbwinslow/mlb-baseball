from pathlib import Path
from unittest.mock import patch

import pytest

from mlb_baseball import chadwick_tools

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet_event"

# Only the two tests below actually invoke the real cwevent/cwgame
# subprocesses — the "no event files" tests raise before ever reaching
# subprocess.run (see _event_files), and the missing_tools()/_run() tests
# mock subprocess entirely. Skip cleanly (not fail) if these aren't
# installed, so the rest of this file and the suite still run — see
# README.md "Requirements".
requires_chadwick_tools = pytest.mark.skipif(
    bool(chadwick_tools.missing_tools()),
    reason=f"cwevent/cwgame not installed: {chadwick_tools.missing_tools()}",
)


def test_missing_tools_empty_when_everything_on_path():
    with patch.object(chadwick_tools.shutil, "which", return_value="/usr/local/bin/x"):
        assert chadwick_tools.missing_tools() == []


def test_missing_tools_reports_absent_tools():
    with patch.object(chadwick_tools.shutil, "which", return_value=None):
        assert set(chadwick_tools.missing_tools()) == set(chadwick_tools.REQUIRED_TOOLS)


def test_run_raises_helpful_error_when_tool_not_found(tmp_path):
    with patch.object(chadwick_tools.subprocess, "run", side_effect=FileNotFoundError()):
        with pytest.raises(RuntimeError, match="not installed or not on PATH"):
            chadwick_tools._run("cwevent", [], tmp_path)


@requires_chadwick_tools
def test_run_cwevent_parses_plays_with_full_field_set():
    df = chadwick_tools.run_cwevent(FIXTURE_DIR, 2024)

    assert len(df) > 0
    assert {"GAME_ID", "BAT_ID", "PIT_ID", "EVENT_TX"} <= set(df.columns)
    assert set(df["GAME_ID"]) == {"ANA202404050", "ANA202404060"}


@requires_chadwick_tools
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
