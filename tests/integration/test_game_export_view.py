"""Regression coverage for gold.game_export (migration 0058) -- a wide,
pre-joined, CSV/Excel/R-ready view over gold.game_feature, with
human-readable team/starter names and the real final score (which lives
on core.game, not gold.game_feature) instead of internal bigint IDs.

Doesn't re-prove any underlying stat's own math (each already has its own
tests elsewhere) -- only that the view's JOINs resolve real names/scores
correctly, including the LEFT JOIN behavior for an upcoming game with no
score/venue/starter resolved yet.
"""

from decimal import Decimal


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
        cur.execute("DELETE FROM core.venue WHERE retro_park_id = 'ATL01'")
    db_conn.commit()


def test_game_export_resolves_team_starter_names_and_real_score(db_conn):
    _reset(db_conn)
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
            "INSERT INTO core.player (retro_id, first_name, last_name) "
            "VALUES ('degrj001', 'Jacob', 'deGrom') RETURNING id"
        )
        (starter_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO core.venue (retro_park_id, name, city, first_year, last_year) "
            "VALUES ('ATL01', 'Test Park', 'Atlanta', 1966, 2025) RETURNING id"
        )
        (venue,) = cur.fetchone()
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type, venue_id) VALUES "
            "('G1', 2024, '2024-04-01', %(atl)s, %(nya)s, 5, 3, 'regular', %(venue)s) "
            "RETURNING id",
            {"atl": atl, "nya": nya, "venue": venue},
        )
        (game_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(game_id, season, game_date, home_team_id, away_team_id, venue_id, "
            "home_starter_id, home_starter_era, home_win, game_instance_key) VALUES "
            "(%(game_id)s, 2024, '2024-04-01', %(atl)s, %(nya)s, %(venue)s, "
            "%(starter_id)s, 2.50, true, 'export-test:G1')",
            {
                "game_id": game_id,
                "atl": atl,
                "nya": nya,
                "venue": venue,
                "starter_id": starter_id,
            },
        )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_team, away_team, home_team_code, away_team_code, "
            "home_score, away_score, venue_name, home_starter, home_starter_era, home_win "
            "FROM gold.game_export WHERE game_instance_key = 'export-test:G1'"
        )
        row = cur.fetchone()

    assert row == (
        "Atlanta Braves",
        "New York Yankees",
        "ATL",
        "NYA",
        5,
        3,
        "Test Park",
        "Jacob deGrom",
        Decimal("2.50"),
        True,
    )

    _reset(db_conn)


def test_game_export_left_joins_gracefully_for_an_upcoming_game(db_conn):
    # An upcoming game has no core.game row yet (core.game only ever holds
    # completed games, matching gold.game_feature's own established
    # design), no venue resolved, no starter resolved -- the view must
    # still return the row with those columns NULL, not drop it or crash.
    _reset(db_conn)
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
            "INSERT INTO gold.game_feature "
            "(mlb_game_pk, season, game_date, home_team_id, away_team_id, "
            "game_instance_key) VALUES "
            "('900123', 2026, '2026-09-01', %(atl)s, %(nya)s, 'export-test:upcoming')",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_team, away_team, home_score, away_score, venue_name, home_starter "
            "FROM gold.game_export WHERE game_instance_key = 'export-test:upcoming'"
        )
        row = cur.fetchone()

    assert row == ("Atlanta Braves", "New York Yankees", None, None, None, None)

    _reset(db_conn)
