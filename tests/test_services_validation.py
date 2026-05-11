"""Tests for baseball.services.validation data quality functions."""

from unittest.mock import MagicMock, patch

import pytest

from baseball.core.enums import ResultStatus, SourceType
from baseball.services import validation


class TestValidateScheduleCompleteness:
    def test_returns_validation_result(self):
        with patch("baseball.services.validation.get_db_connection",
                   return_value=MagicMock()):
            result = validation.validate_schedule_completeness(
                season=2024, db_url=None
            )
            assert hasattr(result, "status")

    def test_no_db_sets_failed(self):
        with patch("baseball.services.validation.get_db_connection",
                   side_effect=Exception("no DB")):
            result = validation.validate_schedule_completeness(
                season=2024, db_url=None
            )
            assert result.status == ResultStatus.FAILED


class TestValidateStatcastCompleteness:
    def test_returns_validation_result(self):
        with patch("baseball.services.validation.get_db_connection",
                   return_value=MagicMock()):
            result = validation.validate_statcast_completeness(
                season=2024, db_url=None
            )
            assert hasattr(result, "status")

    def test_no_db_sets_failed(self):
        with patch("baseball.services.validation.get_db_connection",
                   side_effect=Exception("no DB")):
            result = validation.validate_statcast_completeness(
                season=2024, db_url=None
            )
            assert result.status == ResultStatus.FAILED


class TestValidateReferentialIntegrity:
    def test_returns_validation_result(self):
        with patch("baseball.services.validation.get_db_connection",
                   return_value=MagicMock()):
            result = validation.validate_referential_integrity(
                season=2024, db_url=None
            )
            assert hasattr(result, "status")

    def test_no_db_sets_failed(self):
        with patch("baseball.services.validation.get_db_connection",
                   side_effect=Exception("no DB")):
            result = validation.validate_referential_integrity(
                season=2024, db_url=None
            )
            assert result.status == ResultStatus.FAILED
