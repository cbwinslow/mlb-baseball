"""The Baseball-Reference pull window must be regular-season only -- this is
the fix for ADR-282 (postseason game-logs leaking into raw.bref_batting /
raw.bref_pitching from 2021 on). `_load_table` calls
pybaseball.batting_stats_range(start_dt, end_dt); these tests pin the window.
"""

from datetime import date

import pytest

from mlb_baseball.connectors import bref


@pytest.mark.parametrize("season", range(bref.FIRST_YEAR, 2027))
def test_window_never_reaches_november(season):
    # November is where Baseball-Reference's daily tool starts returning
    # World Series game-logs; pybaseball's own batting_stats_bref() wrapper
    # ends at {season}-11-30, which is exactly the bug.
    _, end_dt = bref._season_window(season)
    end = date.fromisoformat(end_dt)
    assert end.year == season
    assert end.month <= 10, f"{season}: window ends {end_dt}, into the postseason"


@pytest.mark.parametrize("season", range(bref.FIRST_YEAR, 2027))
def test_window_starts_mid_march(season):
    start_dt, _ = bref._season_window(season)
    start = date.fromisoformat(start_dt)
    assert (start.year, start.month, start.day) == (season, 3, 15)


@pytest.mark.parametrize("season", range(2008, 2026))
def test_every_completed_season_has_an_explicit_sourced_end_date(season):
    # Not the {season}-10-01 default: each completed season carries its real
    # last regular-season game date (core.game, game_type in
    # ('regular','playoff')), so a late Game 162 / Game 163 tiebreaker is
    # not truncated.
    assert season in bref._REGULAR_SEASON_END


def test_in_progress_season_falls_back_to_default_end():
    # 2026 is live; no sourced end date yet -> {season}-10-01 default.
    assert 2026 not in bref._REGULAR_SEASON_END
    assert bref._season_window(2026)[1] == "2026-10-01"


def test_load_table_passes_the_window_to_pybaseball(monkeypatch):
    captured = {}

    def fake_range(start_dt, end_dt):
        captured["args"] = (start_dt, end_dt)
        import pandas as pd

        return pd.DataFrame()

    monkeypatch.setattr(bref, "call_with_retry", lambda fn, *a: fn(*a))
    bref._load_table(conn=None, table="raw.bref_batting", fn=fake_range, season=2023)

    assert captured["args"] == ("2023-03-15", "2023-10-01")
