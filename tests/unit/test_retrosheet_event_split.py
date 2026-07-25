from pathlib import Path

from mlb_baseball.connectors.retrosheet_event import _split_by_year

NO_TEAM_FILES_ZIP = (
    Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet_event" / "no_team_files.zip"
)


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
