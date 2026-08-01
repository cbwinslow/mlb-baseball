"""Regression coverage for mlb_baseball.model.speed -- prior-season team
baserunning speed via Statcast Sprint Speed (ADR-041).
"""

from decimal import Decimal

from mlb_baseball.model import features, speed


def _ensure_speed_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_sprint_speed')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.statcast_sprint_speed "
                "(player_id text, team_id text, team text, sprint_speed text, "
                "competitive_runs text, _season text)"
            )
    db_conn.commit()


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_sprint_speed')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.statcast_sprint_speed")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_compute_weights_by_competitive_runs_and_matches_mlb_team_id_directly(db_conn):
    # Two ATL players in 2023: one everyday player (150 competitive runs
    # at 28.0 ft/s), one bench player (10 runs at 30.0 ft/s) -- the
    # weighted average must lean heavily toward the everyday player, not
    # a plain (28.0 + 30.0) / 2 = 29.0.
    #   weighted = (28.0*150 + 30.0*10) / (150+10) = 4500/160 = 28.125
    _reset(db_conn)
    _ensure_speed_table(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 9999, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 9999, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        atl, nya = teams["ATL"], teams["NYA"]
        cur.execute(
            "INSERT INTO raw.statcast_sprint_speed "
            "(player_id, team_id, team, sprint_speed, competitive_runs, _season) VALUES "
            "('1001', '144', 'ATL', '28.0', '150', '2023'), "
            "('1002', '144', 'ATL', '30.0', '10', '2023'), "
            # A player with 0 competitive runs must be excluded (division
            # safety, and a 0-sample row carries no real speed signal).
            "('1003', '144', 'ATL', '99.0', '0', '2023'), "
            # 2024 data must NOT count toward the 2024 game (leakage).
            "('1001', '144', 'ATL', '20.0', '150', '2024')"
        )
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) "
            "VALUES ('G1', 2024, '2024-04-01', %s, %s, 5, 3, 'regular')",
            (atl, nya),
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = speed.compute(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT home_speed_prior, away_speed_prior FROM gold.game_feature")
        (home_prior, away_prior) = cur.fetchone()

    assert abs(home_prior - Decimal("28.125")) < Decimal("0.001")
    assert away_prior is None  # NYA has no raw.statcast_sprint_speed rows

    _reset(db_conn)


def test_compute_returns_zero_without_sprint_speed_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.statcast_sprint_speed")
    db_conn.commit()

    assert speed.compute(db_conn) == 0


def test_health_check_runs_cleanly_against_an_empty_database():
    checks = speed.health_check()
    assert len(checks) == 1
    assert all(c.name for c in checks)
