
"""
================================================================================
Retry Utilities
Date: 2026-05-09

Common retry logic for source operations.
================================================================================
"""

from tenacity import (
    before_sleep_log,
    retry,
    stop_after_attempt,
    wait_exponential,
)
from baseball.core.logging import get_logger


logger = get_logger(__name__)


def retry_on_http_errors(
    max_attempts: int = 3,
    base_wait: int = 2,
):
    """Decorator for retrying on HTTP errors.

    Args:
        max_attempts: Maximum retry attempts
        base_wait: Base wait time in seconds

    Returns:
        Retry decorator
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=base_wait, max=60),
        before_sleep=before_sleep_log(logger, 'WARNING'),
        reraise=True,
    )