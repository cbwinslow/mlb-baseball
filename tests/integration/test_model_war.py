"""Regression coverage for mlb_baseball.model.war -- prior-season team
WAR (ADR-038).
"""

from decimal import Decimal

from mlb_baseball.model import features, war


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player_war")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_compute_uses_prior_season_only_and_resolves_bref_team_codes(db_conn):
    # core.player_war uses bref's own team codes (LAD), core.team uses
    # Retrosheet's (LAN) -- confirmed directly they differ, see module
    # docstring. Also confirms the lag: a 2024 game must use 2023's WAR,
    # never 2024's own (still-accumulating, and would leak future games
    # in this same season if it were used instead).
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('LAN', 'Los Angeles', 'Dodgers', 1958, 2025, 119), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        lan, nya = teams["LAN"], teams["NYA"]
        cur.execute(
            "INSERT INTO core.player (retro_id, first_name, last_name) "
            "VALUES ('playa001', 'A', 'One'), ('playb001', 'B', 'Two') "
            "RETURNING id"
        )
        players = [row[0] for row in cur.fetchall()]
        cur.execute(
            "INSERT INTO core.player_war (player_id, season, is_pitcher, team_code, war) VALUES "
            "(%s, 2023, false, 'LAD', 5.0), "  # counts toward 2024's prior_war
            "(%s, 2023, true, 'LAD', 3.0), "  # counts toward 2024's prior_war
            "(%s, 2024, false, 'LAD', 99.0)",  # must NOT count -- same season, leakage
            (players[0], players[1], players[0]),
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
    updated = war.compute(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT home_war_prior, away_war_prior FROM gold.game_feature")
        (home_prior, away_prior) = cur.fetchone()

    assert home_prior == Decimal("8.0")  # 5.0 + 3.0 from 2023 only, not +99.0 from 2024
    assert away_prior is None  # NYA has no core.player_war rows in this fixture

    _reset(db_conn)


def test_compute_leaves_war_prior_null_when_no_player_war_data_exists(db_conn):
    # core.player_war is a real, migration-created core table (unlike
    # raw.retrosheet_event/raw.mlb_schedule) -- always present, so the
    # thing worth testing is graceful behavior when it's simply EMPTY
    # (e.g. mlb conform hasn't populated it yet), not a missing table.
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('LAN', 'Los Angeles', 'Dodgers', 1958, 2025, 119), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        lan, nya = teams["LAN"], teams["NYA"]
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
    updated = war.compute(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT home_war_prior, away_war_prior FROM gold.game_feature")
        (home_prior, away_prior) = cur.fetchone()
    assert home_prior is None
    assert away_prior is None

    _reset(db_conn)
