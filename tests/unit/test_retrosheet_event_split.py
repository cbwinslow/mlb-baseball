from pathlib import Path

import pytest

from mlb_baseball.connectors.retrosheet_event import _split_by_year, _year_of

FIXTURE_ZIP = (
    Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet_event" / "decade.zip"
)
NO_TEAM_FILES_ZIP = (
    Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet_event" / "no_team_files.zip"
)


@pytest.mark.parametrize(
    ("filename", "expected_year"),
    [
        ("1910BOS.EVA", 1910),
        ("1910.EDA", 1910),
        ("BOS1910.ROS", 1910),
        ("WS11910.ROS", 1910),
        ("TEAM1910", 1910),
        ("2024ANA.EVA", 2024),
        ("no_year_here", None),
    ],
)
def test_year_of_extracts_four_digit_year(filename, expected_year):
    assert _year_of(filename) == expected_year


def test_split_by_year_separates_a_two_year_archive(tmp_path):
    import zipfile

    with zipfile.ZipFile(FIXTURE_ZIP) as zf:
        zf.extractall(tmp_path)

    year_dirs = _split_by_year(tmp_path)

    assert set(year_dirs) == {2024, 2025}
    assert (year_dirs[2024] / "2024ANA.EVA").exists()
    assert (year_dirs[2024] / "TEAM2024").exists()
    assert (year_dirs[2024] / "ANA2024.ROS").exists()
    assert not (year_dirs[2024] / "2025ANA.EVA").exists()
    assert (year_dirs[2025] / "2025ANA.EVA").exists()


def test_split_by_year_creates_empty_team_file_when_archive_has_none(tmp_path):
    # Regression: the Negro League PBP archive (allevr.zip) bundles only
    # whole-league {year}.EVR files, no TEAM{year}/.ROS files at all.
    # cwevent/cwgame refuse to run without *a* team file present, even
    # though it doesn't need to contain anything — this crashed a real
    # bootstrap run on year 1947 with "Can't find teamfile" before the fix.
    import zipfile

    with zipfile.ZipFile(NO_TEAM_FILES_ZIP) as zf:
        zf.extractall(tmp_path)

    year_dirs = _split_by_year(tmp_path)

    assert set(year_dirs) == {1947}
    team_file = year_dirs[1947] / "TEAM1947"
    assert team_file.exists()
    assert team_file.read_text() == ""
