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


def test_migration_0081_structure_and_syntax():
    """Verify migration 0081 creates pitcher_arsenal and sgp views."""
    mig_path = (
        Path(__file__).resolve().parent.parent.parent
        / "migrations"
        / "0081_deep_modeling_serving_views.sql"
    )
    assert mig_path.exists(), "Migration 0081 must exist"

    sql_content = mig_path.read_text(encoding="utf-8")

    assert "CREATE OR REPLACE VIEW serve.pitcher_arsenal" in sql_content
    assert "CREATE OR REPLACE VIEW serve.sgp_matchup_grid" in sql_content
    assert "CREATE OR REPLACE VIEW serve.batted_ball_profile" in sql_content

    assert "estimated_stuff_plus" in sql_content
    assert "estimated_location_plus" in sql_content
    assert "home_expected_runs" in sql_content
    assert "home_hard_hit_pct" in sql_content
