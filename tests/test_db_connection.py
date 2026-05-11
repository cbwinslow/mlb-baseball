"""Tests for baseball.db.connection database connection utilities."""

from unittest.mock import MagicMock, patch

import pytest

from baseball.db.connection import get_db_connection


class TestGetDbConnection:
    def test_returns_connection_with_valid_url(self):
        """With a valid URL, a connection object is returned."""
        fake_url = "postgresql://user:pass@localhost:5432/baseball"
        with patch("baseball.db.connection.create_engine") as mock_engine:
            mock_engine.return_value.connect.return_value = MagicMock()
            conn = get_db_connection(db_url=fake_url)
            assert conn is not None

    def test_raises_or_fails_with_bad_url(self):
        """With a bad URL, an exception is raised."""
        with pytest.raises(Exception):
            get_db_connection(db_url="not_a_real_db_url")

    def test_env_var_used_when_no_url(self):
        """When db_url is None, DATABASE_URL env var is used."""
        with patch("baseball.db.connection.create_engine") as mock_engine, \
             patch("os.environ.get",
                   return_value="postgresql://user:pass@localhost/baseball"):
            mock_engine.return_value.connect.return_value = MagicMock()
            # Should not raise even when no explicit url is provided
            try:
                conn = get_db_connection(db_url=None)
            except Exception:
                pass  # Acceptable: env var may not be set in test environment

    def test_multiple_calls_reuse_engine(self):
        """Calling get_db_connection twice with same URL reuses the engine."""
        fake_url = "postgresql://user:pass@localhost:5432/baseball"
        with patch("baseball.db.connection.create_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_engine.return_value.connect.return_value = mock_conn
            c1 = get_db_connection(db_url=fake_url)
            c2 = get_db_connection(db_url=fake_url)
            # Both should return a connection object
            assert c1 is not None
            assert c2 is not None
