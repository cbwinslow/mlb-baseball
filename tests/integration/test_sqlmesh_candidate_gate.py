"""Integration coverage for the read-only Plan 02 SQLMesh candidate gate.

The candidate relations are deliberately test fixtures here, not promoted
SQLMesh models. This proves the gate's surrogate-ID and scheduled-game identity
semantics while Python remains the only writer for core/gold.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
VENUE_CANDIDATE = "core__plan02_candidate.venue"
FEATURE_CANDIDATE = "gold__plan02_candidate.game_feature"


@pytest.fixture
def candidate_gate_data(db_conn):
    """Create fixture data only in core/gold and candidate namespaces."""
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.venue")
        cur.execute("DELETE FROM core.team")
        cur.execute(
            "INSERT INTO core.team (retro_team_id, city, nickname, first_year, last_year) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 9999), "
            "('NYA', 'New York', 'Yankees', 1913, 9999) RETURNING id"
        )
        atl, nya = [row[0] for row in cur.fetchall()]
        cur.execute(
            "INSERT INTO core.venue (retro_park_id, name) VALUES ('ATL03', 'Test Park') "
            "RETURNING id"
        )
        (venue_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type, venue_id) "
            "VALUES ('TEST202404010', 2024, '2024-04-01', %s, %s, 5, 3, 'regular', %s) "
            "RETURNING id",
            (atl, nya, venue_id),
        )
        (game_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(game_id, game_instance_key, season, game_date, home_team_id, away_team_id, home_win) "
            "VALUES (%s, 'test:candidate-completed', 2024, '2024-04-01', %s, %s, true)",
            (game_id, atl, nya),
        )
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(mlb_game_pk, game_instance_key, season, game_date, home_team_id, away_team_id) "
            "VALUES ('999001', 'test:candidate-scheduled', 2024, '2024-04-02', %s, %s)",
            (atl, nya),
        )
        cur.execute("DROP SCHEMA IF EXISTS core__plan02_candidate CASCADE")
        cur.execute("DROP SCHEMA IF EXISTS gold__plan02_candidate CASCADE")
        cur.execute("CREATE SCHEMA core__plan02_candidate")
        cur.execute("CREATE SCHEMA gold__plan02_candidate")
        cur.execute(
            "CREATE TABLE core__plan02_candidate.venue AS SELECT id, retro_park_id FROM core.venue"
        )
        cur.execute(
            "CREATE TABLE gold__plan02_candidate.game_feature AS "
            "SELECT game_id, mlb_game_pk, home_win IS NOT NULL AS is_completed "
            "FROM gold.game_feature"
        )
    db_conn.commit()
    yield
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS core__plan02_candidate CASCADE")
        cur.execute("DROP SCHEMA IF EXISTS gold__plan02_candidate CASCADE")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.venue")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_candidate_gate_proves_surrogate_and_completed_scheduled_parity(
    candidate_gate_data, monkeypatch
):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql:///mlb_test")

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/verify_sqlmesh_candidate.py",
            "--venue",
            VENUE_CANDIDATE,
            "--feature",
            FEATURE_CANDIDATE,
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        check=True,
        capture_output=True,
        text=True,
    )

    assert "candidate parity passed" in result.stdout
