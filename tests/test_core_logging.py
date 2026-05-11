"""Tests for baseball.core.logging."""

import logging

import pytest

from baseball.core.logging import get_logger, setup_logging


class TestGetLogger:
    def test_returns_logger(self):
        logger = get_logger("test")
        assert isinstance(logger, logging.Logger)

    def test_logger_name(self):
        logger = get_logger("my_module")
        assert logger.name == "my_module"

    def test_different_names_return_different_loggers(self):
        logger1 = get_logger("module_a")
        logger2 = get_logger("module_b")
        assert logger1.name != logger2.name

    def test_same_name_returns_same_logger(self):
        logger1 = get_logger("shared_module")
        logger2 = get_logger("shared_module")
        assert logger1 is logger2


class TestSetupLogging:
    def test_returns_logger(self):
        logger = setup_logging("test_setup")
        assert isinstance(logger, logging.Logger)

    def test_logger_has_handler(self):
        logger = setup_logging("test_handler")
        assert len(logger.handlers) > 0

    def test_without_rich(self):
        logger = setup_logging("test_no_rich", use_rich=False)
        assert isinstance(logger, logging.Logger)
        has_stream_handler = any(
            isinstance(h, logging.StreamHandler) for h in logger.handlers
        )
        assert has_stream_handler

    def test_custom_level(self):
        logger = setup_logging("test_level", level=logging.DEBUG)
        assert logger.level == logging.DEBUG
