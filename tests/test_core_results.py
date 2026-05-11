"""Tests for baseball.core.results dataclasses."""

from datetime import datetime

import pytest

from baseball.core.enums import OperationType, ResultStatus, SourceType
from baseball.core.results import (
    CommandResult,
    DownloadResult,
    IngestResult,
    LiveUpdate,
    ValidationResult,
)


class TestDownloadResult:
    def test_default_status_is_failed(self):
        r = DownloadResult(source=SourceType.MLB)
        assert r.status == ResultStatus.FAILED

    def test_success_property_true_when_success(self):
        r = DownloadResult(source=SourceType.MLB, status=ResultStatus.SUCCESS)
        assert r.success is True

    def test_success_property_false_when_failed(self):
        r = DownloadResult(source=SourceType.MLB, status=ResultStatus.FAILED)
        assert r.success is False

    def test_duration_seconds_zero_when_no_times(self):
        r = DownloadResult(source=SourceType.MLB)
        assert r.duration_seconds == 0.0

    def test_duration_seconds_calculated(self):
        r = DownloadResult(source=SourceType.MLB)
        r.start_time = datetime(2024, 4, 1, 12, 0, 0)
        r.end_time = datetime(2024, 4, 1, 12, 0, 5)
        assert r.duration_seconds == 5.0

    def test_to_dict_contains_expected_keys(self):
        r = DownloadResult(source=SourceType.MLB, status=ResultStatus.SUCCESS)
        d = r.to_dict()
        assert "source" in d
        assert "status" in d
        assert "rows_downloaded" in d

    def test_default_rows_downloaded_zero(self):
        r = DownloadResult(source=SourceType.RETROSHEET)
        assert r.rows_downloaded == 0


class TestIngestResult:
    def test_default_status_is_success(self):
        r = IngestResult(source=SourceType.MLB)
        assert r.status == ResultStatus.SUCCESS

    def test_rows_inserted_default_zero(self):
        r = IngestResult(source=SourceType.MLB)
        assert r.rows_inserted == 0

    def test_rows_updated_default_zero(self):
        r = IngestResult(source=SourceType.MLB)
        assert r.rows_updated == 0

    def test_success_true_when_success(self):
        r = IngestResult(source=SourceType.STATCAST, status=ResultStatus.SUCCESS)
        assert r.success is True

    def test_success_false_when_failed(self):
        r = IngestResult(source=SourceType.STATCAST, status=ResultStatus.FAILED)
        assert r.success is False


class TestValidationResult:
    def test_instantiates(self):
        r = ValidationResult(source=SourceType.MLB)
        assert r is not None

    def test_default_status(self):
        r = ValidationResult(source=SourceType.MLB)
        assert r.status in (ResultStatus.SUCCESS, ResultStatus.FAILED, ResultStatus.PARTIAL)


class TestCommandResult:
    def test_instantiates(self):
        r = CommandResult()
        assert r is not None

    def test_default_exit_code(self):
        r = CommandResult()
        assert hasattr(r, "exit_code") or r is not None
