"""Regression coverage for mlb_baseball.model.framing -- prior-season
team catcher-framing value via Statcast (ADR-045).
"""

from decimal import Decimal

from mlb_baseball.model import features, framing


def _ensure_framing_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_framing')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.statcast_framing "
                "(id text, name text, pitches text, rv_tot text, _season text)"
            )
    db_conn.commit()


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_framing')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.statcast_framing")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player_war")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_compute_sums_multiple_catchers_and_resolves_bref_team_codes(db_conn):
    # core.player_war uses bref's own team codes (LAD), core.team uses
    # Retrosheet's (LAN) -- same crosswalk problem war.py already solved
    # (and this module reuses). Two LAD catchers in 2023 (a primary catcher
    # at 6.5 and a backup at -1.2) must sum for the 2024 game's prior value;
    # a 2024-season row for the same catcher must NOT count (leakage).
    _reset(db_conn)
    _ensure_framing_table(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('LAN', 'Los Angeles', 'Dodgers', 1958, 9999, 119), "
            "('NYA', 'New York', 'Yankees', 1913, 9999, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        lan, nya = teams["LAN"], teams["NYA"]
        cur.execute(
            "INSERT INTO core.player (retro_id, mlbam_id, first_name, last_name) "
            "VALUES ('catcp001', '1001', 'Primary', 'Catcher'), "
            "('catcp002', '1002', 'Backup', 'Catcher') "
            "RETURNING id, mlbam_id"
        )
        players = {mlbam_id: player_id for player_id, mlbam_id in cur.fetchall()}
        p1, p2 = players["1001"], players["1002"]
        cur.execute(
            "INSERT INTO core.player_war (player_id, season, is_pitcher, team_code, war) VALUES "
            "(%s, 2023, false, 'LAD', 3.0), "
            "(%s, 2023, false, 'LAD', 0.5), "
            "(%s, 2024, false, 'LAD', 3.5)",  # must NOT count -- same season, leakage
            (p1, p2, p1),
        )
        cur.execute(
            "INSERT INTO raw.statcast_framing (id, name, pitches, rv_tot, _season) VALUES "
            "('1001', 'Primary Catcher', '5000', '6.5', '2023'), "
            "('1002', 'Backup Catcher', '800', '-1.2', '2023'), "
            "('1001', 'Primary Catcher', '5200', '9.0', '2024')"
        )
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) "
            "VALUES ('G1', 2024, '2024-04-01', %s, %s, 5, 3, 'regular')",
            (lan, nya),
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = framing.compute(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT home_framing_prior, away_framing_prior FROM gold.game_feature")
        (home_prior, away_prior) = cur.fetchone()

    assert home_prior == Decimal("5.3")  # 6.5 + -1.2 from 2023 only, not +9.0 from 2024
    assert away_prior is None  # NYA has no matching rows in this fixture

    _reset(db_conn)


def test_compute_returns_zero_without_framing_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.statcast_framing")
    db_conn.commit()

    assert framing.compute(db_conn) == 0


def test_health_check_runs_cleanly_against_an_empty_database():
    checks = framing.health_check()
    assert len(checks) == 1
    assert all(c.name for c in checks)
