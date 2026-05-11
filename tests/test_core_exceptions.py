"""Tests for baseball.core.exceptions."""

import pytest

from baseball.core.exceptions import (
    BaseballException,
    ConfigException,
    DatabaseException,
    DownloadException,
    IngestException,
    LiveException,
    SourceException,
    ValidationException,
)


class TestBaseballException:
    def test_basic_raise(self):
        with pytest.raises(BaseballException):
            raise BaseballException("test error")

    def test_message(self):
        exc = BaseballException("test message")
        assert str(exc) == "test message"

    def test_is_exception(self):
        assert issubclass(BaseballException, Exception)


class TestSourceException:
    def test_is_baseball_exception(self):
        assert issubclass(SourceException, BaseballException)

    def test_raise(self):
        with pytest.raises(SourceException):
            raise SourceException("source error")

    def test_catch_as_baseball_exception(self):
        with pytest.raises(BaseballException):
            raise SourceException("source error")


class TestDownloadException:
    def test_is_source_exception(self):
        assert issubclass(DownloadException, SourceException)

    def test_raise(self):
        with pytest.raises(DownloadException):
            raise DownloadException("download failed")

    def test_catch_as_baseball_exception(self):
        with pytest.raises(BaseballException):
            raise DownloadException("download failed")


class TestIngestException:
    def test_is_source_exception(self):
        assert issubclass(IngestException, SourceException)

    def test_raise(self):
        with pytest.raises(IngestException):
            raise IngestException("ingest failed")


class TestValidationException:
    def test_is_baseball_exception(self):
        assert issubclass(ValidationException, BaseballException)

    def test_raise(self):
        with pytest.raises(ValidationException):
            raise ValidationException("validation failed")


class TestConfigException:
    def test_is_baseball_exception(self):
        assert issubclass(ConfigException, BaseballException)

    def test_raise(self):
        with pytest.raises(ConfigException):
            raise ConfigException("config error")


class TestDatabaseException:
    def test_is_baseball_exception(self):
        assert issubclass(DatabaseException, BaseballException)

    def test_raise(self):
        with pytest.raises(DatabaseException):
            raise DatabaseException("db error")


class TestLiveException:
    def test_is_baseball_exception(self):
        assert issubclass(LiveException, BaseballException)

    def test_raise(self):
        with pytest.raises(LiveException):
            raise LiveException("live error")
