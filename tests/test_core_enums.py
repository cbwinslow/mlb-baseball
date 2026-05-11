"""Tests for baseball.core.enums."""

import pytest

from baseball.core.enums import (
    DataGranularity,
    OperationType,
    ResultStatus,
    SourceType,
)


class TestSourceType:
    def test_mlb_value(self):
        assert SourceType.MLB == "mlb"

    def test_retrosheet_value(self):
        assert SourceType.RETROSHEET == "retrosheet"

    def test_statcast_value(self):
        assert SourceType.STATCAST == "statcast"

    def test_lahman_value(self):
        assert SourceType.LAHMAN == "lahman"

    def test_fangraphs_value(self):
        assert SourceType.FANGRAPHS == "fangraphs"

    def test_espn_value(self):
        assert SourceType.ESPN == "espn"

    def test_all_members_present(self):
        names = {m.name for m in SourceType}
        assert "MLB" in names
        assert "RETROSHEET" in names
        assert "STATCAST" in names

    def test_string_comparison(self):
        assert str(SourceType.MLB) == "mlb"


class TestResultStatus:
    def test_success_value(self):
        assert ResultStatus.SUCCESS == "success"

    def test_failed_value(self):
        assert ResultStatus.FAILED == "failed"

    def test_partial_value(self):
        assert ResultStatus.PARTIAL == "partial"

    def test_skipped_value(self):
        assert ResultStatus.SKIPPED == "skipped"

    def test_all_four_members(self):
        assert len(ResultStatus) == 4


class TestOperationType:
    def test_download_value(self):
        assert OperationType.DOWNLOAD == "download"

    def test_ingest_value(self):
        assert OperationType.INGEST == "ingest"

    def test_validate_value(self):
        assert OperationType.VALIDATE == "validate"

    def test_normalize_value(self):
        assert OperationType.NORMALIZE == "normalize"


class TestDataGranularity:
    def test_pitch_value(self):
        assert DataGranularity.PITCH == "pitch"

    def test_game_value(self):
        assert DataGranularity.GAME == "game"

    def test_team_value(self):
        assert DataGranularity.TEAM == "team"

    def test_league_value(self):
        assert DataGranularity.LEAGUE == "league"
