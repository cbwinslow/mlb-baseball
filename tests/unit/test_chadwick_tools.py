import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mlb_baseball import chadwick_tools

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet_event"
DECADE_FIXTURE_ZIP = FIXTURE_DIR / "decade.zip"
BOX_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet_box"

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


@pytest.mark.parametrize(
    ("filename", "expected_year"),
    [
        ("1910BOS.EVA", 1910),
        ("1910.EDA", 1910),
        ("1900.EBN", 1900),  # box-score files use the same leading-year convention
        ("BOS1910.ROS", 1910),
        ("WS11910.ROS", 1910),  # team code ending in a digit, must not confuse the split
        ("TEAM1910", 1910),
        ("2024ANA.EVA", 2024),
        ("no_year_here", None),
    ],
)
def test_year_of_extracts_four_digit_year(filename, expected_year):
    assert chadwick_tools.year_of(filename) == expected_year


def test_split_by_year_separates_a_two_year_archive(tmp_path):
    with zipfile.ZipFile(DECADE_FIXTURE_ZIP) as zf:
        zf.extractall(tmp_path)

    year_dirs = chadwick_tools.split_by_year(tmp_path)

    assert set(year_dirs) == {2024, 2025}
    assert (year_dirs[2024] / "2024ANA.EVA").exists()
    assert (year_dirs[2024] / "TEAM2024").exists()
    assert (year_dirs[2024] / "ANA2024.ROS").exists()
    assert not (year_dirs[2024] / "2025ANA.EVA").exists()
    assert (year_dirs[2025] / "2025ANA.EVA").exists()


def test_write_team_file_matches_retrosheets_documented_format(tmp_path):
    # retrosheet.org/eventfile.htm: "contains the team codes and team names
    # in the particular season" — confirmed against a real bundled TEAM
    # file's exact layout (team_id,league,city,nickname) before relying on it.
    chadwick_tools.write_team_file(
        tmp_path, 1900, [("BRO", "NL", "Brooklyn", "Dodgers"), ("NY1", "NL", "New York", "Giants")]
    )

    content = (tmp_path / "TEAM1900").read_text()
    assert content == "BRO,NL,Brooklyn,Dodgers\nNY1,NL,New York,Giants\n"


@requires_chadwick_tools
def test_run_cwbox_parses_real_box_score_file_with_real_team_and_roster_files():
    result = chadwick_tools.run_cwbox(BOX_FIXTURE_DIR, 1900)

    assert set(result) == {
        "game",
        "batting",
        "fielding",
        "pitching",
        *chadwick_tools.SUPPLEMENTARY_LISTS,
    }
    game = result["game"]
    assert len(game) == 2
    assert set(game["game_id"]) == {"BRO190004210", "BRO190004280"}
    # Confirms the real (not empty) TEAM file resolved actual team codes/names —
    # this is exactly the field that comes back blank without one (ADR-012).
    row = game[game["game_id"] == "BRO190004210"].iloc[0]
    assert row["visitor"] == "NY1"
    assert row["visitor_name"] == "Giants"
    assert row["home"] == "BRO"
    assert row["home_name"] == "Dodgers"

    batting = result["batting"]
    assert len(batting) > 0
    assert {"game_id", "team", "id", "lname", "fname", "ab", "h", "hr"} <= set(batting.columns)

    fielding = result["fielding"]
    assert len(fielding) > 0
    assert {"pos", "po", "a", "e"} <= set(fielding.columns)

    pitching = result["pitching"]
    assert len(pitching) > 0
    assert {"id", "gs", "outs", "h", "r", "er", "dec"} <= set(pitching.columns)


def test_run_cwbox_raises_on_directory_with_no_box_files(tmp_path):
    with pytest.raises(RuntimeError, match="no box-score files"):
        chadwick_tools.run_cwbox(tmp_path, 1900)


def test_parse_cwbox_xml_handles_multiple_boxscore_elements():
    xml_text = (
        '<boxscore game_id="G1" date="1900/01/01">'
        '<linescore away_runs="1" home_runs="2" away_hits="0" away_errors="0" '
        'home_hits="0" home_errors="0"></linescore>'
        '<players team="AAA"><player id="p1" lname="Last" fname="First" slot="1" seq="1" pos="9">'
        '<batting ab="4" r="1" h="2"/><fielding pos="9" outs="27" po="1" a="0" e="0"/>'
        "</player></players>"
        '<pitching team="AAA"><pitcher id="p2" gs="1"/></pitching>'
        "</boxscore>"
        '<boxscore game_id="G2" date="1900/01/02">'
        '<linescore away_runs="3" home_runs="4" away_hits="0" away_errors="0" '
        'home_hits="0" home_errors="0"></linescore>'
        "<players></players>"
        "</boxscore>"
    )

    result = chadwick_tools._parse_cwbox_xml(xml_text)

    assert list(result["game"]["game_id"]) == ["G1", "G2"]
    assert result["batting"].iloc[0]["h"] == "2"
    assert result["fielding"].iloc[0]["po"] == "1"


def test_parse_cwbox_xml_extracts_supplementary_event_lists():
    xml_text = (
        '<boxscore game_id="G1" date="1900/01/01">'
        '<linescore away_runs="1" home_runs="2" away_hits="0" away_errors="0" '
        'home_hits="0" home_errors="0"></linescore>'
        "<players></players>"
        '<doubles><double batter="p1" pitcher="p2" inning="3" half="0"/></doubles>'
        '<triples><triple batter="p3" pitcher="p2" inning="5" half="1"/></triples>'
        '<homeruns><homerun batter="p1" pitcher="p2" inning="7" half="0" runners="1" '
        'outs="1" location=""/></homeruns>'
        '<stolenbases><stolenbase runner="p1" pitcher="p2" catcher="p4" inning="2" '
        'half="0" base="2" pickoff="0"/></stolenbases>'
        '<doubleplays><doubleplay inning="4" half="1" player1="p5" player2="p6"/>'
        "</doubleplays>"
        '<tripleplays><tripleplay inning="6" half="0" player1="p5" player2="p6" '
        'player3="p7"/></tripleplays>'
        '<sacbunts><sacbunt batter="p3" pitcher="p2" inning="1" half="1"/></sacbunts>'
        "</boxscore>"
        # A second game with none of these — confirms a genuinely-absent
        # container element doesn't crash the parse (box.find() returns None).
        '<boxscore game_id="G2" date="1900/01/02">'
        '<linescore away_runs="0" home_runs="0" away_hits="0" away_errors="0" '
        'home_hits="0" home_errors="0"></linescore>'
        "<players></players>"
        "</boxscore>"
    )

    result = chadwick_tools._parse_cwbox_xml(xml_text)

    assert list(result["double"]["game_id"]) == ["G1"]
    assert result["double"].iloc[0]["batter"] == "p1"
    assert list(result["triple"]["game_id"]) == ["G1"]
    assert result["homerun"].iloc[0]["runners"] == "1"
    assert result["stolenbase"].iloc[0]["base"] == "2"
    assert result["doubleplay"].iloc[0]["player1"] == "p5"
    assert result["tripleplay"].iloc[0]["player3"] == "p7"
    assert result["sacbunt"].iloc[0]["inning"] == "1"
    # G2 contributed no rows to any supplementary list — the DataFrames
    # exist (created by run_cwbox's caller regardless) but stay G1-only.
    assert "G2" not in set(result["double"]["game_id"])
