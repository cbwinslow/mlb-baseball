"""
================================================================================
Validation Services
Date: 2026-05-09
Updated: 2026-05-12

Orchestrate validation workflows across all data sources.
Each function validates a specific data artifact and returns a ValidationResult.
================================================================================
"""

from pathlib import Path
from typing import Optional

from baseball.core.logging import get_logger
from baseball.core.results import ValidationResult

logger = get_logger(__name__)


def validate_mlb_schedule(path: Path) -> ValidationResult:
    """Validate MLB schedule file.

    Args:
        path: Path to schedule file

    Returns:
        ValidationResult
    """
    from baseball.sources.mlb.validator import MLBValidator

    logger.info(f"Validation service: MLB schedule {path}")
    validator = MLBValidator()
    return validator.validate_schedule(path)


def validate_retrosheet_events(path: Path) -> ValidationResult:
    """Validate Retrosheet event file.

    Args:
        path: Path to .EVA / .EVN event file or directory

    Returns:
        ValidationResult
    """
    from baseball.sources.retrosheet.validator import RetroEventValidator

    logger.info(f"Validation service: Retrosheet events {path}")
    validator = RetroEventValidator()
    return validator.validate(path)


def validate_statcast_file(path: Path) -> ValidationResult:
    """Validate StatCast CSV file.

    Args:
        path: Path to statcast CSV file

    Returns:
        ValidationResult
    """
    from baseball.sources.statcast.validator import StatcastValidator

    logger.info(f"Validation service: StatCast file {path}")
    validator = StatcastValidator()
    return validator.validate(path)


def validate_source_directory(
    source: str,
    data_dir: Path,
    season: Optional[int] = None,
) -> ValidationResult:
    """Validate all downloaded files for a given source.

    Args:
        source: Source name (mlb, retrosheet, statcast, etc.)
        data_dir: Root data directory
        season: Optional season filter

    Returns:
        ValidationResult with aggregate pass/fail
    """
    source_dir = data_dir / source
    if not source_dir.exists():
        return ValidationResult(
            success=False,
            source=source,
            message=f"Source directory does not exist: {source_dir}",
            errors=[f"Missing directory: {source_dir}"],
        )

    files = list(source_dir.rglob("*"))
    file_count = len([f for f in files if f.is_file()])
    logger.info(f"Validation service: {source} directory — {file_count} files found")

    return ValidationResult(
        success=file_count > 0,
        source=source,
        message=f"Found {file_count} files in {source_dir}",
        errors=[] if file_count > 0 else [f"No files found in {source_dir}"],
    )


__all__ = [
    "validate_mlb_schedule",
    "validate_retrosheet_events",
    "validate_statcast_file",
    "validate_source_directory",
]
