"""Unit tests for Serving Layer Views (SERVE-02, ADR-123)."""

from pathlib import Path


def test_migration_0080_structure_and_syntax():
    """Verify migration 0080 creates ros_team_standings and matchup_dossier views."""
    mig_path = (
        Path(__file__).resolve().parent.parent.parent
        / "migrations"
        / "0080_ros_and_stacked_serving_views.sql"
    )
    assert mig_path.exists(), "Migration 0080 must exist"

    sql_content = mig_path.read_text(encoding="utf-8")

    # Verify both view definitions exist
    assert "CREATE OR REPLACE VIEW serve.ros_team_standings" in sql_content
    assert "CREATE OR REPLACE VIEW serve.matchup_dossier" in sql_content

    # Verify key statistical columns are calculated
    assert "pythagorean_win_pct" in sql_content
    assert "run_differential" in sql_content
    assert "gbm_home_win_prob" in sql_content
    assert "log5_home_win_prob" in sql_content
    assert "elo_home_win_prob" in sql_content
    assert "park_factor" in sql_content
