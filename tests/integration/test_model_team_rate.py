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


def _ensure_retrosheet_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_event ("
                "game_id text, bat_home_id text, event_cd text, "
                "ab_fl text, sf_fl text, _season text)"
            )
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if not cur.fetchone()[0]:
            cur.execute("CREATE TABLE raw.retrosheet_gameinfo (gid text, gametype text)")
    db_conn.commit()


def test_compute_rolling_rate_stats_match_hand_calculation(db_conn):
    # ATL (home) in G1: 1 single, 1 double, 1 unintentional BB, 1
    # intentional BB, 1 HBP, 1 strikeout, 2 generic outs.
    #   AB = single + double + 2 generic outs + strikeout = 5
    #      (ab_fl='T' on every batted/struck-out plate appearance below)
    #   H = 1B(1) + 2B(1) = 2; TB = 1*1 + 2*1 = 3
    #   BB = ubb(1) + ibb(1) = 2; HBP = 1; SF = 0; SO = 1
    #   OBP = (H+BB+HBP)/(AB+BB+HBP+SF) = (2+2+1)/(5+2+1+0) = 5/8 = 0.625
    #   SLG = TB/AB = 3/5 = 0.6
    #   AVG = H/AB = 2/5 = 0.4; ISO = SLG-AVG = 0.2
    #   PA = AB+BB+HBP+SF = 5+2+1+0 = 8
    #   BB% = 2/8 = 0.25; K% = 1/8 = 0.125
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    with db_conn.cursor() as cur:
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
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2020, '2020-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2020, '2020-04-08', %(atl)s, %(nya)s, 2, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('G2', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, event_cd, ab_fl, sf_fl, _season) VALUES "
            "('G1', '1', '20', 'T', 'F', '2020'), "  # single
            "('G1', '1', '21', 'T', 'F', '2020'), "  # double
            "('G1', '1', '14', 'F', 'F', '2020'), "  # unintentional BB
            "('G1', '1', '15', 'F', 'F', '2020'), "  # intentional BB
            "('G1', '1', '16', 'F', 'F', '2020'), "  # HBP
            "('G1', '1', '3',  'T', 'F', '2020'), "  # strikeout
            "('G1', '1', '2',  'T', 'F', '2020'), "  # generic out
            "('G1', '1', '2',  'T', 'F', '2020'), "  # generic out
            "('G1', '0', '2',  'T', 'F', '2020'), "  # NYA (away) -- minimal
            # G2 needs at least one event row per side for the rolling
            # window's "current row" to exist at all.
            "('G2', '1', '2', 'T', 'F', '2020'), "
            "('G2', '0', '2', 'T', 'F', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = team_rate.compute(db_conn)
    db_conn.commit()

    assert updated == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_obp, f.home_slg, f.home_iso, "
            "f.home_bb_pct, f.home_k_pct "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    assert rows["G1"] == (None, None, None, None, None)  # first game
    g2 = rows["G2"]
    assert g2[0] == Decimal("0.625")  # OBP
    assert g2[1] == Decimal("0.6")  # SLG
    assert g2[2] == Decimal("0.2")  # ISO
    assert g2[3] == Decimal("0.25")  # BB%
    assert g2[4] == Decimal("0.125")  # K%

    _reset(db_conn)


def test_compute_returns_zero_without_retrosheet_event_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
    db_conn.commit()

    assert team_rate.compute(db_conn) == 0
