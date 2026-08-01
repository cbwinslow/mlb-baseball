"""Regression coverage for mlb_baseball.model.offense -- rolling team
wOBA computed from raw.retrosheet_event (ADR-036).
"""

from decimal import Decimal

from mlb_baseball.model import features, offense


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


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.retrosheet_event")
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.retrosheet_gameinfo")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_compute_rolling_woba_matches_hand_calculation(db_conn):
    # ATL (home, batting when bat_home_id='1') in G1: 1 single, 1 BB,
    # 1 HBP, 1 generic out (AB=2: the single + the out). Entering G2:
    #   numerator = 0.690*1 + 0.722*1 + 0.878*1 = 2.290
    #   denominator = AB(2) + uBB(1) + SF(0) + HBP(1) = 4
    #   wOBA = 2.290 / 4 = 0.5725
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
            "('G1', '1', '14', 'F', 'F', '2020'), "  # BB
            "('G1', '1', '16', 'F', 'F', '2020'), "  # HBP
            "('G1', '1', '2', 'T', 'F', '2020'), "  # generic out
            "('G1', '0', '2', 'T', 'F', '2020'), "  # NYA (away) batting -- minimal
            # G2 needs at least one event row per side for the rolling
            # window's "current row" to exist at all -- otherwise there's
            # nothing for the window to attach the entering-G2 value to.
            "('G2', '1', '2', 'T', 'F', '2020'), "
            "('G2', '0', '2', 'T', 'F', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = offense.compute(db_conn)
    db_conn.commit()

    assert updated == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_woba "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1] for r in cur.fetchall()}

    assert rows["G1"] is None  # first game -- nothing prior
    assert rows["G2"] == Decimal("0.5725")

    _reset(db_conn)


def test_compute_returns_zero_without_retrosheet_event_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
    db_conn.commit()

    assert offense.compute(db_conn) == 0


def _ensure_playbyplay_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.mlb_playbyplay ("
                "game_pk text, at_bat_index text, inning text, half_inning text, "
                "pitcher_id text, event_type text, outs text, _season text)"
            )
    db_conn.commit()


def test_compute_live_rolling_woba_matches_hand_calculation(db_conn):
    # ATL (home, batting when half_inning='bottom') in G1: 1 single, 1
    # walk, 1 hit_by_pitch, 1 field_out (AB=2: the single + the out).
    # Same numbers as the Retrosheet-based test above, same hand-computed
    # result: wOBA = 2.290 / 4 = 0.5725.
    _reset(db_conn)
    _ensure_playbyplay_table(db_conn)
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
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('MLB910001', '910001', 2026, '2026-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('MLB910002', '910002', 2026, '2026-04-08', %(atl)s, %(nya)s, 2, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.mlb_playbyplay "
            "(game_pk, at_bat_index, inning, half_inning, pitcher_id, event_type, outs, _season) "
            "VALUES "
            "('910001', '0', '1', 'bottom', '1', 'single', '0', '2026'), "
            "('910001', '1', '1', 'bottom', '1', 'walk', '0', '2026'), "
            "('910001', '2', '1', 'bottom', '1', 'hit_by_pitch', '0', '2026'), "
            "('910001', '3', '1', 'bottom', '1', 'field_out', '1', '2026'), "
            "('910001', '4', '1', 'top', '2', 'field_out', '1', '2026'), "
            "('910002', '0', '1', 'bottom', '1', 'field_out', '1', '2026'), "
            "('910002', '1', '1', 'top', '2', 'field_out', '1', '2026')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = offense.compute_live(db_conn)
    db_conn.commit()

    assert updated == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_woba, f.away_woba "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    assert rows["MLB910001"] == (None, None)  # nothing prior
    g2 = rows["MLB910002"]
    assert abs(g2[0] - Decimal("0.5725")) < Decimal("0.0001")
    # NYA's only G1 plate appearance was a field_out (AB=1, no hits/BB/
    # HBP) -- a real, valid (if tiny-sample) wOBA of exactly 0, not NULL.
    assert g2[1] == Decimal("0")

    _reset(db_conn)


def test_compute_live_does_not_overwrite_retrosheet_derived_values(db_conn):
    _reset(db_conn)
    _ensure_playbyplay_table(db_conn)
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
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) "
            "VALUES ('MLB910003', '910003', 2026, '2026-04-01', %(atl)s, %(nya)s, 5, 3, 'regular')",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()
    features.build(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature SET home_woba = 0.333 WHERE mlb_game_pk = '910003'"
        )
    db_conn.commit()

    offense.compute_live(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT home_woba FROM gold.game_feature WHERE mlb_game_pk = '910003'")
        (woba,) = cur.fetchone()
    assert woba == Decimal("0.333")

    _reset(db_conn)


def test_compute_live_returns_zero_without_playbyplay_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_playbyplay")
    db_conn.commit()

    assert offense.compute_live(db_conn) == 0


def test_health_check_flags_an_implausible_value(db_conn):
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
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) "
            "VALUES ('G1', 2024, '2024-04-01', %s, %s, 5, 3, 'regular')",
            (atl, nya),
        )
    db_conn.commit()
    features.build(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature SET home_woba = 5.0 "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G1')"
        )
    db_conn.commit()

    check = offense.health_check()[0]

    assert not check.ok
    assert "1 rows" in check.detail

    _reset(db_conn)
