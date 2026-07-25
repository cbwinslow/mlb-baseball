from mlb_baseball.connectors import retrosheet


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")


def test_season_years_lists_only_numeric_season_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(retrosheet, "REPO_DIR", tmp_path)
    _touch(tmp_path / "seasons" / "1901" / "placeholder")
    _touch(tmp_path / "seasons" / "2025" / "placeholder")
    _touch(tmp_path / "seasons" / "README.md")  # not a season dir, must be skipped

    assert retrosheet.season_years() == [1901, 2025]


def test_event_files_matches_only_true_event_files(tmp_path, monkeypatch):
    monkeypatch.setattr(retrosheet, "REPO_DIR", tmp_path)
    season_dir = tmp_path / "seasons" / "2025"
    season_dir.mkdir(parents=True)
    for name in [
        "2025ATL.EVN",
        "2025ANA.EVA",
        "2025ALCS.EVE",
        "2025.EBA",
        "ATL2025.ROS",
        "TEAM2025",
    ]:
        (season_dir / name).write_text("")

    files = retrosheet._event_files(2025)

    assert [f.name for f in files] == ["2025ALCS.EVE", "2025ANA.EVA", "2025ATL.EVN"]
