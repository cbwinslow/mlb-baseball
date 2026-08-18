"""Regression coverage for mlb_baseball.model.offense.compute_wrc_plus
(ADR-037). The underlying wOBA computation is covered by
test_model_offense.py -- this focuses on the park/league-adjustment layer.
"""

from decimal import Decimal

from mlb_baseball.model import features, offense, park


def _ensure_retrosheet_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_event ("
                "game_id text, bat_home_id text, event_cd text, "
                "ab_fl text, sf_fl text, _season text)"
            )
        else:
            cur.execute("ALTER TABLE raw.retrosheet_event ADD COLUMN IF NOT EXISTS ab_fl text")
            cur.execute("ALTER TABLE raw.retrosheet_event ADD COLUMN IF NOT EXISTS sf_fl text")
            cur.execute("ALTER TABLE raw.retrosheet_event ADD COLUMN IF NOT EXISTS _season text")
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if not cur.fetchone()[0]:
            cur.execute("CREATE TABLE raw.retrosheet_gameinfo (gid text, gametype text)")
    db_conn.commit()


def _reset(db_conn):
    # DROPs raw.retrosheet_event/retrosheet_gameinfo rather than DELETEing
    # their rows -- see test_model_offense.py's identical _reset for the
    # full explanation (issue #7): several test_model_*.py files each
    # create their own minimal stub schema for these two tables, and a
    # stale stub from an earlier file's run breaks later files' schema
    # expectations. Dropping means _ensure_retrosheet_tables always
    # recreates exactly this file's own shape, regardless of run order.
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.venue")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_compute_wrc_plus_returns_zero_without_retrosheet_gameinfo_table(db_conn):
    # Issue #9 item 2: compute_wrc_plus()'s own SQL joins
    # raw.retrosheet_gameinfo too, but only retrosheet_event was gated --
    # see test_model_offense.py's identical regression for compute() for
    # the full explanation (retrosheet_event/retrosheet_gameinfo are landed
    # by two different connectors).
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, bat_home_id text, event_cd text, "
            "ab_fl text, sf_fl text, _season text)"
        )
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
    db_conn.commit()

    assert offense.compute_wrc_plus(db_conn) == 0

    _reset(db_conn)


def test_compute_wrc_plus_matches_hand_calculation(db_conn):
    # park_factor(V, 2023) = 240 (2020 trailing data: ATL home 7+5=12,
    # road 2+3=5 -- see test_model_park.py for this exact derivation).
    # G3 (2023): ATL (home) bats 1 single/1 BB/1 HBP/1 out -> team_woba
    # 0.5725 (see test_model_offense.py). NYA (away) bats 1 single/1 out.
    # League G3 combined: ubb=1, hbp=1, 1B=2, AB=4 -> league_woba = 0.528.
    # Entering G4: wRC+ = (((0.5725-0.528)/1.20)+1) / (240/100) * 100
    #                   = 43.2118055555556 (verified via Python Fraction
    #                     arithmetic before writing this assertion).
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147), "
            "('BOS', 'Boston', 'Red Sox', 1901, 2025, 111) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        atl, nya, bos = teams["ATL"], teams["NYA"], teams["BOS"]
        cur.execute(
            "INSERT INTO core.venue (retro_park_id, name, mlb_venue_id) "
            "VALUES ('ATL03', 'Truist Park', 4705) RETURNING id"
        )
        (venue_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type, venue_id) VALUES "
            "('H1', 2020, '2020-04-01', %(atl)s, %(nya)s, 7, 5, 'regular', %(venue)s), "
            "('R1', 2020, '2020-04-05', %(bos)s, %(atl)s, 2, 3, 'regular', NULL), "
            "('G3', 2023, '2023-04-01', %(atl)s, %(nya)s, 1, 1, 'regular', %(venue)s), "
            "('G4', 2023, '2023-04-08', %(atl)s, %(nya)s, 1, 1, 'regular', %(venue)s)",
            {"atl": atl, "nya": nya, "bos": bos, "venue": venue_id},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G3', 'regular'), ('G4', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, event_cd, ab_fl, sf_fl, _season) VALUES "
            "('G3', '1', '20', 'T', 'F', '2023'), "
            "('G3', '1', '14', 'F', 'F', '2023'), "
            "('G3', '1', '16', 'F', 'F', '2023'), "
            "('G3', '1', '2', 'T', 'F', '2023'), "
            "('G3', '0', '20', 'T', 'F', '2023'), "
            "('G3', '0', '2', 'T', 'F', '2023'), "
            "('G4', '1', '2', 'T', 'F', '2023'), "
            "('G4', '0', '2', 'T', 'F', '2023')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    park.compute(db_conn)
    db_conn.commit()
    offense.compute(db_conn)
    db_conn.commit()
    updated = offense.compute_wrc_plus(db_conn)
    db_conn.commit()

    assert updated == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_wrc_plus "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1] for r in cur.fetchall()}

    assert rows["G3"] is None  # first game of 2023 for both teams -- nothing prior
    assert abs(rows["G4"] - Decimal("43.2118055555556")) < Decimal("0.0001")

    _reset(db_conn)


def test_league_average_hitter_in_a_neutral_park_is_exactly_100(db_conn):
    # Algebraic sanity check baked into a real test: if team_woba equals
    # league_woba (an exactly-average hitter) and park_factor is 100 (a
    # neutral park), wRC+ must reduce to exactly 100 -- that's required by
    # wRC+'s own definition, not just a property of some specific fixture.
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
            "('G1', 2023, '2023-04-01', %(atl)s, %(nya)s, 1, 1, 'regular'), "
            "('G2', 2023, '2023-04-02', %(atl)s, %(nya)s, 1, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('G2', 'regular')"
        )
        # G1: both sides bat identically -- team wOBA entering G2 will
        # equal league wOBA entering G2 exactly, by symmetry.
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, event_cd, ab_fl, sf_fl, _season) VALUES "
            "('G1', '1', '20', 'T', 'F', '2023'), "
            "('G1', '1', '2', 'T', 'F', '2023'), "
            "('G1', '0', '20', 'T', 'F', '2023'), "
            "('G1', '0', '2', 'T', 'F', '2023'), "
            "('G2', '1', '2', 'T', 'F', '2023'), "
            "('G2', '0', '2', 'T', 'F', '2023')"
        )
        # No venue on G2 -- park_factor stays NULL, but the CASE guard
        # requires it non-NULL, so set it directly to isolate the formula
        # itself from park.py's own separate computation.
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    offense.compute(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature SET park_factor = 100 "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G2')"
        )
    db_conn.commit()
    offense.compute_wrc_plus(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_wrc_plus FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id WHERE g.retro_game_id = 'G2'"
        )
        (wrc_plus,) = cur.fetchone()

    assert wrc_plus == Decimal("100.00000000000000")

    _reset(db_conn)
