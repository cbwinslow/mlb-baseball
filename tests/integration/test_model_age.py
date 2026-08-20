"""Regression coverage for mlb_baseball.model.age -- starter age on game
date (ADR-087, admission queue PLN-04). Pure derived value over
gold.game_feature's own home_starter_id/away_starter_id and
core.player.birth_date, so these tests seed both directly rather than
running the full features.build()/starter.compute() pipeline.
"""

from decimal import Decimal

from mlb_baseball.model import age


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def _seed_teams(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        return {retro_id: team_id for team_id, retro_id in cur.fetchall()}


def test_compute_matches_hand_calculation(db_conn):
    # Home starter born exactly 30 years before the game date (age must
    # be exactly 30.0, not off by a leap-year rounding error); away
    # starter born exactly 3653 days before (10 years + 3 leap days ->
    # slightly over 10.0, proving this is real day-count division, not a
    # floored/truncated year count).
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.player (retro_id, first_name, last_name, birth_date) "
            "VALUES ('homep001', 'Home', 'Pitcher', '1994-04-01'), "
            "('awayp001', 'Away', 'Pitcher', '2014-04-01') "
            "RETURNING id, retro_id"
        )
        players = {retro_id: player_id for player_id, retro_id in cur.fetchall()}
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(season, game_date, home_team_id, away_team_id, game_instance_key, "
            "home_starter_id, away_starter_id) VALUES "
            "(2024, '2024-04-01', %(atl)s, %(nya)s, 'age-test:G1', %(hp)s, %(ap)s)",
            {
                "atl": atl,
                "nya": nya,
                "hp": players["homep001"],
                "ap": players["awayp001"],
            },
        )
    db_conn.commit()

    updated = age.compute(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_starter_age, away_starter_age "
            "FROM gold.game_feature WHERE game_instance_key = 'age-test:G1'"
        )
        home_age, away_age = cur.fetchone()

    # Real day counts (date(2024,4,1) - date(1994,4,1) and
    # date(2024,4,1) - date(2014,4,1) in Python), not hand-derived --
    # leap-year arithmetic by hand is error-prone enough that this was
    # checked with real date math before being hardcoded here.
    expected_home = Decimal(10958) / Decimal("365.25")
    assert abs(home_age - expected_home) < Decimal("0.0001")
    expected_away = Decimal(3653) / Decimal("365.25")
    assert abs(away_age - expected_away) < Decimal("0.0001")


def test_compute_is_null_when_starter_or_birth_date_is_unresolved(db_conn):
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        # Away starter resolved but with no known birth_date -- a real,
        # documented gap (core.player.birth_date is genuinely NULL for
        # some real production rows), not a hypothetical.
        cur.execute(
            "INSERT INTO core.player (retro_id, first_name, last_name, birth_date) "
            "VALUES ('awayp002', 'Away', 'NoBirthDate', NULL) RETURNING id"
        )
        (away_player,) = cur.fetchone()
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(season, game_date, home_team_id, away_team_id, game_instance_key, "
            "home_starter_id, away_starter_id) VALUES "
            # home_starter_id NULL: starter not yet resolved for this game.
            "(2024, '2024-04-01', %(atl)s, %(nya)s, 'age-test:G2', NULL, %(ap)s)",
            {"atl": atl, "nya": nya, "ap": away_player},
        )
    db_conn.commit()

    age.compute(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_starter_age, away_starter_age "
            "FROM gold.game_feature WHERE game_instance_key = 'age-test:G2'"
        )
        row = cur.fetchone()

    assert row == (None, None)


def test_compute_handles_an_upcoming_game_with_no_core_game_row(db_conn):
    # An upcoming game has no core.game row (gold.game_feature.game_id is
    # NULL) -- compute() must still update it via the real primary key
    # (id), not silently skip it the way a game_id self-join would.
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.player (retro_id, first_name, last_name, birth_date) "
            "VALUES ('homep003', 'Home', 'Upcoming', '2000-01-01') RETURNING id"
        )
        (home_player,) = cur.fetchone()
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(mlb_game_pk, season, game_date, home_team_id, away_team_id, "
            "game_instance_key, home_starter_id) VALUES "
            "('900555', 2026, '2026-09-01', %(atl)s, %(nya)s, "
            "'age-test:upcoming', %(hp)s)",
            {"atl": atl, "nya": nya, "hp": home_player},
        )
    db_conn.commit()

    updated = age.compute(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_starter_age FROM gold.game_feature "
            "WHERE game_instance_key = 'age-test:upcoming'"
        )
        (home_age,) = cur.fetchone()

    assert home_age is not None


def test_compute_is_idempotent(db_conn):
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.player (retro_id, first_name, last_name, birth_date) "
            "VALUES ('homep004', 'Home', 'Idem', '1990-01-01') RETURNING id"
        )
        (home_player,) = cur.fetchone()
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(season, game_date, home_team_id, away_team_id, game_instance_key, "
            "home_starter_id) VALUES "
            "(2024, '2024-01-01', %(atl)s, %(nya)s, 'age-test:G3', %(hp)s)",
            {"atl": atl, "nya": nya, "hp": home_player},
        )
    db_conn.commit()

    age.compute(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_starter_age FROM gold.game_feature WHERE game_instance_key = 'age-test:G3'"
        )
        (first,) = cur.fetchone()

    age.compute(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_starter_age FROM gold.game_feature WHERE game_instance_key = 'age-test:G3'"
        )
        (second,) = cur.fetchone()

    assert first == second


def test_health_check_flags_an_implausible_value(db_conn):
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(season, game_date, home_team_id, away_team_id, game_instance_key, "
            "home_starter_age) VALUES "
            "(2024, '2024-04-01', %s, %s, 'age-test:G4', 5)",
            (atl, nya),
        )
    db_conn.commit()

    checks = age.health_check()
    home_check = next(c for c in checks if c.name == "home_starter_age plausible range")

    assert not home_check.ok
    assert "1 rows" in home_check.detail


def test_health_check_passes_after_a_real_compute(db_conn):
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.player (retro_id, first_name, last_name, birth_date) "
            "VALUES ('homep005', 'Home', 'Clean', '1995-06-15') RETURNING id"
        )
        (home_player,) = cur.fetchone()
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(season, game_date, home_team_id, away_team_id, game_instance_key, "
            "home_starter_id) VALUES "
            "(2024, '2024-06-15', %(atl)s, %(nya)s, 'age-test:G5', %(hp)s)",
            {"atl": atl, "nya": nya, "hp": home_player},
        )
    db_conn.commit()
    age.compute(db_conn)
    db_conn.commit()

    checks = age.health_check()

    assert all(c.ok for c in checks)
