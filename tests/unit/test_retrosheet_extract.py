from pathlib import Path

from mlb_baseball.connectors.retrosheet import CSV_NAMES, _extract_csvs

FIXTURE_ZIP = Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet" / "2025csvs.zip"


def test_extracts_all_seven_csvs_with_season_column():
    dataframes = _extract_csvs(2025, FIXTURE_ZIP.read_bytes())

    assert set(dataframes) == set(CSV_NAMES)
    for name, df in dataframes.items():
        assert len(df) > 0, name
        assert (df["_season"] == "2025").all(), name


def test_plays_columns_include_known_retrosheet_fields():
    dataframes = _extract_csvs(2025, FIXTURE_ZIP.read_bytes())

    plays_columns = set(dataframes["plays"].columns)
    assert {"gid", "batter", "pitcher", "single", "double", "hr"} <= plays_columns
