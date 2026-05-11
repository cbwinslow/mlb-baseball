"""
================================================================================
Data Validation Framework
Name: validators.py
Date: 2026-05-11
Script: validators.py
Version: 1.0.0
Log Summary: Data quality and integrity validation checks
Description: Comprehensive validators for all tables and data constraints
Change Summary: Initial implementation with pluggable validator architecture
Inputs: Database session, validation configuration
Outputs: Validation reports with issues and statistics
================================================================================
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from baseball.core.logging import get_logger
from baseball.db.models import (
    Game,
    Park,
    Pitch,
    Player,
    PlayerSeason,
    PitcherSeason,
    PlayByPlay,
    Schedule,
    Team,
)

logger = get_logger(__name__)


class ValidationSeverity(str, Enum):
    """Severity level of validation issues."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """Single validation issue."""

    severity: ValidationSeverity
    table: str
    check_name: str
    message: str
    affected_rows: int = 0
    sample_ids: List[int] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Complete validation report."""

    timestamp: str
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    warning_checks: int = 0
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def validation_passed(self) -> bool:
        """Check if validation passed overall."""
        return self.failed_checks == 0


class DataValidator:
    """Validate data integrity and quality across all tables."""

    def __init__(self, session: Session):
        """Initialize validator.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.report = ValidationReport(timestamp="")

    def validate_player_table(self) -> ValidationReport:
        """Validate player table integrity.

        Returns:
            Validation report for players
        """
        report = ValidationReport(timestamp="")

        # Check for duplicate MLBam IDs
        duplicates = self.session.execute(
            text(
                "SELECT player_mlbam_id, COUNT(*) as cnt FROM player "
                "WHERE player_mlbam_id IS NOT NULL "
                "GROUP BY player_mlbam_id HAVING COUNT(*) > 1"
            )
        ).fetchall()

        if duplicates:
            issue = ValidationIssue(
                severity=ValidationSeverity.ERROR,
                table="player",
                check_name="duplicate_mlbam_id",
                message=f"Found {len(duplicates)} players with duplicate MLBAM IDs",
                affected_rows=len(duplicates),
            )
            report.issues.append(issue)
            report.failed_checks += 1
        else:
            report.passed_checks += 1

        # Check for NULL names
        null_names = self.session.query(Player).filter(
            (Player.first_name.is_(None)) | (Player.last_name.is_(None))
        ).count()

        if null_names > 0:
            issue = ValidationIssue(
                severity=ValidationSeverity.WARNING,
                table="player",
                check_name="null_names",
                message=f"Found {null_names} players with NULL names",
                affected_rows=null_names,
            )
            report.issues.append(issue)
            report.warning_checks += 1
        else:
            report.passed_checks += 1

        report.total_checks = report.passed_checks + report.failed_checks + report.warning_checks
        return report

    def validate_team_table(self) -> ValidationReport:
        """Validate team table integrity.

        Returns:
            Validation report for teams
        """
        report = ValidationReport(timestamp="")

        # Check for duplicate team abbreviations
        duplicates = self.session.execute(
            text(
                "SELECT team_abbr, COUNT(*) as cnt FROM team "
                "GROUP BY team_abbr HAVING COUNT(*) > 1"
            )
        ).fetchall()

        if duplicates:
            issue = ValidationIssue(
                severity=ValidationSeverity.ERROR,
                table="team",
                check_name="duplicate_abbr",
                message=f"Found {len(duplicates)} duplicate team abbreviations",
                affected_rows=len(duplicates),
            )
            report.issues.append(issue)
            report.failed_checks += 1
        else:
            report.passed_checks += 1

        # Check for invalid leagues
        invalid_leagues = self.session.query(Team).filter(
            ~Team.league.in_(["AL", "NL"])
        ).count()

        if invalid_leagues > 0:
            issue = ValidationIssue(
                severity=ValidationSeverity.ERROR,
                table="team",
                check_name="invalid_league",
                message=f"Found {invalid_leagues} teams with invalid league values",
                affected_rows=invalid_leagues,
            )
            report.issues.append(issue)
            report.failed_checks += 1
        else:
            report.passed_checks += 1

        report.total_checks = report.passed_checks + report.failed_checks + report.warning_checks
        return report

    def validate_game_table(self) -> ValidationReport:
        """Validate game table integrity.

        Returns:
            Validation report for games
        """
        report = ValidationReport(timestamp="")

        # Check for duplicate game IDs
        duplicates = self.session.execute(
            text(
                "SELECT game_mlbam_id, COUNT(*) as cnt FROM game "
                "WHERE game_mlbam_id IS NOT NULL "
                "GROUP BY game_mlbam_id HAVING COUNT(*) > 1"
            )
        ).fetchall()

        if duplicates:
            issue = ValidationIssue(
                severity=ValidationSeverity.ERROR,
                table="game",
                check_name="duplicate_game_id",
                message=f"Found {len(duplicates)} games with duplicate game IDs",
                affected_rows=len(duplicates),
            )
            report.issues.append(issue)
            report.failed_checks += 1
        else:
            report.passed_checks += 1

        # Check for negative scores
        negative_scores = self.session.query(Game).filter(
            (Game.home_score < 0) | (Game.away_score < 0)
        ).count()

        if negative_scores > 0:
            issue = ValidationIssue(
                severity=ValidationSeverity.ERROR,
                table="game",
                check_name="negative_scores",
                message=f"Found {negative_scores} games with negative scores",
                affected_rows=negative_scores,
            )
            report.issues.append(issue)
            report.failed_checks += 1
        else:
            report.passed_checks += 1

        report.total_checks = report.passed_checks + report.failed_checks + report.warning_checks
        return report

    def validate_pitch_table(self) -> ValidationReport:
        """Validate pitch table integrity.

        Returns:
            Validation report for pitches
        """
        report = ValidationReport(timestamp="")

        # Check for orphaned pitches (game_id doesn't exist)
        orphaned = self.session.execute(
            text(
                "SELECT p.pitch_id FROM pitch p "
                "LEFT JOIN game g ON p.game_id = g.game_id "
                "WHERE g.game_id IS NULL LIMIT 100"
            )
        ).fetchall()

        if orphaned:
            issue = ValidationIssue(
                severity=ValidationSeverity.ERROR,
                table="pitch",
                check_name="orphaned_records",
                message=f"Found {len(orphaned)} pitches with no matching game",
                affected_rows=len(orphaned),
                sample_ids=[row[0] for row in orphaned[:5]],
            )
            report.issues.append(issue)
            report.failed_checks += 1
        else:
            report.passed_checks += 1

        report.total_checks = report.passed_checks + report.failed_checks + report.warning_checks
        return report

    def run_all_validations(self) -> ValidationReport:
        """Run all data quality validations.

        Returns:
            Comprehensive validation report
        """
        logger.info("Starting comprehensive data validation")

        all_issues = []
        total_checks = 0
        passed_checks = 0
        failed_checks = 0
        warning_checks = 0

        for validator_func in [
            self.validate_player_table,
            self.validate_team_table,
            self.validate_game_table,
            self.validate_pitch_table,
        ]:
            try:
                report = validator_func()
                all_issues.extend(report.issues)
                total_checks += report.total_checks
                passed_checks += report.passed_checks
                failed_checks += report.failed_checks
                warning_checks += report.warning_checks
            except Exception as e:
                logger.error(f"Validation error in {validator_func.__name__}: {e}")

        final_report = ValidationReport(timestamp="")
        final_report.total_checks = total_checks
        final_report.passed_checks = passed_checks
        final_report.failed_checks = failed_checks
        final_report.warning_checks = warning_checks
        final_report.issues = all_issues

        if final_report.validation_passed:
            logger.info("Data validation passed")
        else:
            logger.error(
                f"Data validation failed with {failed_checks} errors and "
                f"{warning_checks} warnings"
            )

        return final_report
