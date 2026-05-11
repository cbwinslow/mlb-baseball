"""Tests for baseball.data constants and utilities."""

from baseball.data import (
    AMERICAN_LEAGUE,
    COMMON_BATTING_STATS,
    COMMON_PITCHING_STATS,
    CURRENT_SEASON,
    MODERN_ERA_START,
    NATIONAL_LEAGUE,
)


class TestDataConstants:
    def test_modern_era_start(self):
        assert MODERN_ERA_START == 1900

    def test_current_season_is_int(self):
        assert isinstance(CURRENT_SEASON, int)

    def test_current_season_reasonable(self):
        assert 2020 <= CURRENT_SEASON <= 2030

    def test_american_league(self):
        assert AMERICAN_LEAGUE == "AL"

    def test_national_league(self):
        assert NATIONAL_LEAGUE == "NL"

    def test_leagues_are_different(self):
        assert AMERICAN_LEAGUE != NATIONAL_LEAGUE


class TestCommonStats:
    def test_batting_stats_is_list(self):
        assert isinstance(COMMON_BATTING_STATS, list)

    def test_batting_stats_not_empty(self):
        assert len(COMMON_BATTING_STATS) > 0

    def test_batting_stats_has_hr(self):
        assert "HR" in COMMON_BATTING_STATS

    def test_batting_stats_has_avg(self):
        assert "AVG" in COMMON_BATTING_STATS

    def test_pitching_stats_is_list(self):
        assert isinstance(COMMON_PITCHING_STATS, list)

    def test_pitching_stats_not_empty(self):
        assert len(COMMON_PITCHING_STATS) > 0

    def test_pitching_stats_has_era(self):
        assert "ERA" in COMMON_PITCHING_STATS

    def test_pitching_stats_has_whip(self):
        assert "WHIP" in COMMON_PITCHING_STATS

    def test_stats_are_strings(self):
        for stat in COMMON_BATTING_STATS:
            assert isinstance(stat, str)
        for stat in COMMON_PITCHING_STATS:
            assert isinstance(stat, str)
