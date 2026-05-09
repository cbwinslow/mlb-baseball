"""
================================================================================
Validation Services
Date: 2026-05-09

Orchestrate validation workflows.
================================================================================
"""

from pathlib import Path

from baseball.core.logging import get_logger
from baseball.core.results import ValidationResult
from baseball.sources.mlb.validator import MLBValidator


logger = get_logger(__name__)


def validate_mlb_schedule(path: Path) -> ValidationResult:
    """Validate MLB schedule file.

    Args:
        path: Path to schedule file

    Returns:
        ValidationResult
    """
    logger.info(f"Validation service: MLB schedule {path}")

    validator = MLBValidator()
    return validator.validate_schedule(path)
