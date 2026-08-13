"""Regression coverage for mlb_baseball.model.team_rate -- prior rolling
team OBP/SLG/ISO/BB%/K% (ADR-061, admission queue OFF-01/02/03) and prior
runs-for/allowed averages (OFF-08/DEF-01).
"""

from decimal import Decimal

from mlb_baseball.model import features, team_rate


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.retrosheet_event")
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.retrosheet_gameinfo")
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.mlb_schedule")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def _insert_three_games(db_conn):
    # ATL home in G1 (5-3 win) and G2 (2-6 loss); G3 is what we assert on.
    # Entering G3: runs_for_avg = (5+2)/2 = 3.5, runs_allowed_avg = (3+6)/2 = 4.5.
    with db_conn.cursor() as cur:
        # Ensure raw.mlb_schedule table exists with all needed columns
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.mlb_schedule (game_id text, game_datetime text, game_date text, "
                "game_type text, status text, home_id text, away_id text, game_num text, venue_id text, "
                "_season text, _loaded_at timestamptz)"
            )
        else:
            # Add missing columns if they don't exist
            cur.execute(
                "ALTER TABLE raw.mlb_schedule ADD COLUMN IF NOT EXISTS game_datetime text, "
                "ADD COLUMN IF NOT EXISTS _loaded_at timestamptz"
            )

        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        atl, nya = teams["ATL"], teams["NYA"]
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 1001, 2020, '2020-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 1002, 2020, '2020-04-08', %(atl)s, %(nya)s, 2, 6, 'regular'), "
            "('G3', 1003, 2020, '2020-04-15', %(atl)s, %(nya)s, 1, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        # Insert schedule records to trigger strict path in features.build()
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, game_datetime, game_date, game_type, status, home_id, away_id, game_num, _season, _loaded_at) "
            "VALUES "
            "('1001', '2020-04-01T18:00:00Z', '2020-04-01', 'R', 'Final', '144', '147', '1', '2020', now()), "
            "('1002', '2020-04-08T18:00:00Z', '2020-04-08', 'R', 'Final', '144', '147', '1', '2020', now()), "
            "('1003', '2020-04-15T18:00:00Z', '2020-04-15', 'R', 'Final', '144', '147', '1', '2020', now())"
        )
    db_conn.commit()


def test_compute_run_environment_matches_hand_calculation(db_conn):
    _reset(db_conn)
    _insert_three_games(db_conn)
    features.build(db_conn, strict=True)
    db_conn.commit()

    updated = team_rate.compute_run_environment(db_conn)
    db_conn.commit()

    assert updated == 3
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_runs_for_avg, f.home_runs_allowed_avg "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    assert rows["G1"] == (None, None)  # first game -- nothing prior
    assert rows["G3"] == (Decimal("3.5"), Decimal("4.5"))

    _reset(db_conn)


def test_compute_run_environment_is_idempotent(db_conn):
    _reset(db_conn)
    _insert_three_games(db_conn)
    features.build(db_conn, strict=True)
    db_conn.commit()

    team_rate.compute_run_environment(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_runs_for_avg FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id WHERE g.retro_game_id = 'G3'"
        )
        (first_run,) = cur.fetchone()

    team_rate.compute_run_environment(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_runs_for_avg FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id WHERE g.retro_game_id = 'G3'"
        )
        (second_run,) = cur.fetchone()

    assert first_run == second_run == Decimal("3.5")

    _reset(db_conn)
