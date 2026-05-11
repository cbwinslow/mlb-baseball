"""Tests for baseball.sources.common utilities."""

import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from baseball.sources.common.checksums import (
    file_checksum,
    string_checksum,
    verify_checksum,
)
from baseball.sources.common.files import (
    get_temp_file,
    load_json,
    save_json,
)
from baseball.sources.common.time import (
    date_range,
    now_utc,
    season_dates,
    to_utc,
)


class TestChecksums:
    def test_string_checksum_returns_string(self):
        result = string_checksum("hello")
        assert isinstance(result, str)
        assert len(result) == 64  # sha256 hex digest

    def test_string_checksum_deterministic(self):
        assert string_checksum("hello") == string_checksum("hello")

    def test_string_checksum_different_inputs(self):
        assert string_checksum("hello") != string_checksum("world")

    def test_file_checksum(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")
        result = file_checksum(test_file)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_verify_checksum_valid(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")
        checksum = file_checksum(test_file)
        assert verify_checksum(test_file, checksum) is True

    def test_verify_checksum_invalid(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")
        assert verify_checksum(test_file, "deadbeef" * 8) is False


class TestFiles:
    def test_save_and_load_json(self, tmp_path):
        data = {"key": "value", "number": 42}
        path = tmp_path / "test.json"
        save_json(data, path)
        loaded = load_json(path)
        assert loaded == data

    def test_save_json_creates_parent_dirs(self, tmp_path):
        data = {"test": True}
        path = tmp_path / "subdir" / "nested" / "data.json"
        save_json(data, path)
        assert path.exists()

    def test_get_temp_file_returns_path(self):
        path = get_temp_file()
        assert isinstance(path, Path)

    def test_get_temp_file_with_suffix(self):
        path = get_temp_file(".csv")
        assert str(path).endswith(".csv")


class TestTime:
    def test_now_utc_returns_datetime(self):
        result = now_utc()
        assert isinstance(result, datetime)

    def test_now_utc_is_utc(self):
        result = now_utc()
        assert result.tzinfo == timezone.utc

    def test_to_utc_naive(self):
        naive = datetime(2024, 1, 1, 12, 0, 0)
        result = to_utc(naive)
        assert result.tzinfo is not None

    def test_to_utc_aware(self):
        aware = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = to_utc(aware)
        assert result.tzinfo == timezone.utc

    def test_date_range(self):
        start = date(2024, 4, 1)
        end = date(2024, 4, 5)
        result = date_range(start, end)
        assert len(result) == 5
        assert result[0] == start
        assert result[-1] == end

    def test_date_range_single_day(self):
        d = date(2024, 6, 15)
        result = date_range(d, d)
        assert len(result) == 1

    def test_season_dates_returns_tuple(self):
        result = season_dates(2024)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_season_dates_opening_before_closing(self):
        opening, closing = season_dates(2024)
        assert opening < closing
