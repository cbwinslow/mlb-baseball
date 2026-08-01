"""Regression coverage for mlb_baseball.model.oaa -- prior-season team
defensive value via Statcast Outs Above Average (ADR-040).
"""

from decimal import Decimal

from mlb_baseball.model import features, oaa


def _ensure_oaa_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_oaa')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.statcast_oaa "
                "(player_id text, display_team_name text, year text, "
                "fielding_runs_prevented text, _season text)"
            )
    db_conn.commit()


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_oaa')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.statcast_oaa")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_compute_sums_multi_position_rows_and_remaps_savant_short_names(db_conn):
    # Statcast Savant's leaderboard is one row per player per SEASON per
    # POSITION, not one row per player-season -- a player who logged time
    # at two positions gets two rows, both of which must count toward
    # their season total (not a duplicate to dedupe). Also exercises the
    # one real name mismatch this module's docstring documents for the
    # diamondbacks: Savant's short "D-backs" vs core.team's "Diamondbacks".
    _reset(db_conn)
    _ensure_oaa_table(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ARI', 'Arizona', 'Diamondbacks', 1998, 9999, 109), "
            "('NYA', 'New York', 'Yankees', 1913, 9999, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        ari, nya = teams["ARI"], teams["NYA"]
        cur.execute(
            "INSERT INTO raw.statcast_oaa "
            "(player_id, display_team_name, year, fielding_runs_prevented, _season) VALUES "
            # Two positions, same player, same 2023 season -- must sum, not overwrite.
            "('1001', 'D-backs', '2023', '4', '2023'), "
            "('1001', 'D-backs', '2023', '-1', '2023'), "
            # A second D-backs player, same season.
            "('1002', 'D-backs', '2023', '2', '2023'), "
            # Same-season data for 2024 must NOT count toward the 2024 game
            # (current-season leakage, same trap as war.py).
            "('1001', 'D-backs', '2024', '99', '2024')"
        )
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) "
            "VALUES ('G1', 2024, '2024-04-01', %s, %s, 5, 3, 'regular')",
            (ari, nya),
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = oaa.compute(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT home_oaa_prior, away_oaa_prior FROM gold.game_feature")
        (home_prior, away_prior) = cur.fetchone()

    # 2023 total: (4 + -1) + 2 = 5, never the 2024 row's 99.
    assert home_prior == Decimal("5")
    assert away_prior is None  # NYA has no raw.statcast_oaa rows in this fixture

    _reset(db_conn)


def test_compute_excludes_unresolved_team_placeholder_rows(db_conn):
    # display_team_name = '---' is a real Savant value (a player with no
    # clear primary team that season) -- must be excluded, not guessed
    # into some team's total.
    _reset(db_conn)
    _ensure_oaa_table(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ARI', 'Arizona', 'Diamondbacks', 1998, 9999, 109), "
            "('NYA', 'New York', 'Yankees', 1913, 9999, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        ari, nya = teams["ARI"], teams["NYA"]
        cur.execute(
            "INSERT INTO raw.statcast_oaa "
            "(player_id, display_team_name, year, fielding_runs_prevented, _season) "
            "VALUES ('1003', '---', '2023', '10', '2023')"
        )
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) "
            "VALUES ('G1', 2024, '2024-04-01', %s, %s, 5, 3, 'regular')",
            (ari, nya),
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    oaa.compute(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT home_oaa_prior, away_oaa_prior FROM gold.game_feature")
        (home_prior, away_prior) = cur.fetchone()
    assert home_prior is None
    assert away_prior is None

    _reset(db_conn)


def test_compute_returns_zero_without_statcast_oaa_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.statcast_oaa")
    db_conn.commit()

    assert oaa.compute(db_conn) == 0


def test_health_check_runs_cleanly_against_an_empty_database():
    checks = oaa.health_check()
    assert len(checks) == 1
    assert all(c.name for c in checks)
