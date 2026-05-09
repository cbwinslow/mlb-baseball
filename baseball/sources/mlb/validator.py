"""
================================================================================
MLB Validator
Date: 2026-05-09

Validation logic for MLB downloaded data.
================================================================================
"""

from pathlib import Path

from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import ValidationResult
from baseball.sources.common.files import load_csv, load_json

logger = get_logger(__name__)


class MLBValidator:
    """Validate MLB data."""

    def __init__(self):
        """Initialize validator."""
        pass

    def validate_schedule(self, path: Path) -> ValidationResult:
        """Validate schedule CSV.

        Args:
            path: Path to schedule CSV

        Returns:
            ValidationResult
        """
        result = ValidationResult(
            source=SourceType.MLB,
            status=ResultStatus.FAILED,
        )

        try:
            df = load_csv(path)

            required_columns = {"game_pk", "game_date", "season", "status"}
            missing = required_columns - set(df.columns)

            if missing:
                result.issues.append(f"Missing columns: {missing}")
                result.status = ResultStatus.FAILED
                return result

            # Check for null values in required columns
            nulls = df[list(required_columns)].isnull().sum()
            if nulls.sum() > 0:
                result.issues.append(f"Found null values: {nulls.to_dict()}")

            result.records_validated = len(df)
            result.records_valid = len(df) - len(df[list(required_columns)].isnull().any(axis=1))
            result.records_invalid = len(df) - result.records_valid

            result.status = (
                ResultStatus.SUCCESS if len(result.issues) == 0 else ResultStatus.PARTIAL
            )

        except Exception as e:
            result.error = str(e)
            result.error_code = "VALIDATION_ERROR"
            logger.exception(f"Validation failed: {e}")

        return result

    def validate_game(self, path: Path) -> ValidationResult:
        """Validate game JSON file.

        Args:
            path: Path to game JSON

        Returns:
            ValidationResult
        """
        result = ValidationResult(
            source=SourceType.MLB,
            status=ResultStatus.FAILED,
        )

        try:
            data = load_json(path)

            # Check basic structure
            if "gamePk" not in data:
                result.issues.append("Missing gamePk in game data")
            if "gameData" not in data:
                result.issues.append("Missing gameData in game data")

            result.records_validated = 1
            result.records_valid = 1 if len(result.issues) == 0 else 0
            result.records_invalid = 1 - result.records_valid

            result.status = (
                ResultStatus.SUCCESS if len(result.issues) == 0 else ResultStatus.PARTIAL
            )

        except Exception as e:
            result.error = str(e)
            result.error_code = "VALIDATION_ERROR"
            logger.exception(f"Validation failed: {e}")

        return result
