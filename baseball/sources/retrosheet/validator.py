"""
================================================================================
Retrosheet Validator
Date: 2026-05-09

Validate Retrosheet data files.
================================================================================
"""

from pathlib import Path

from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import ValidationResult

logger = get_logger(__name__)


class RetroEventFileValidator:
    """Validate Retrosheet event files."""

    def __init__(self):
        """Initialize validator."""
        pass

    def validate_event_file(self, path: Path) -> ValidationResult:
        """Validate event file format.

        Args:
            path: Path to event file

        Returns:
            ValidationResult
        """
        result = ValidationResult(
            source=SourceType.RETROSHEET,
            status=ResultStatus.FAILED,
        )

        try:
            with open(path) as f:
                lines = f.readlines()

            result.records_validated = len(lines)
            valid_count = 0
            issues = []

            # Check required line types
            has_id = False
            has_plays = False

            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue

                parts = line.split(",")
                line_type = parts[0]

                if line_type == "id":
                    has_id = True
                elif line_type == "play":
                    has_plays = True
                    # Validate play line format
                    if len(parts) < 7:
                        issues.append(f"Play line {line_num}: insufficient fields")

                valid_count += 1

            if not has_id:
                issues.append("Missing id line")
            if not has_plays:
                issues.append("No play lines found")

            result.records_valid = valid_count
            result.records_invalid = len(lines) - valid_count
            result.issues = issues
            result.status = ResultStatus.SUCCESS if len(issues) == 0 else ResultStatus.PARTIAL

        except Exception as e:
            result.error = str(e)
            result.error_code = "VALIDATION_ERROR"
            logger.exception(f"Validation failed: {e}")

        return result
