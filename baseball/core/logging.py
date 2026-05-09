"""
================================================================================
Shared Logging Setup
Date: 2026-05-09

Centralized logging configuration for the baseball platform.
================================================================================
"""

import logging
import sys

from rich.logging import RichHandler


def setup_logging(
    name: str,
    level: int = logging.INFO,
    use_rich: bool = True,
) -> logging.Logger:
    """
    Setup a logger with optional Rich formatting.

    Args:
        name: Logger name (usually __name__)
        level: Logging level (default: INFO)
        use_rich: Use Rich formatting (default: True)

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Remove existing handlers to avoid duplication
    logger.handlers.clear()

    if use_rich:
        handler = RichHandler(
            rich_tracebacks=True,
            show_time=True,
            show_path=False,
        )
    else:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)

    logger.addHandler(handler)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get or create a logger with standard setup."""
    return logging.getLogger(name)
