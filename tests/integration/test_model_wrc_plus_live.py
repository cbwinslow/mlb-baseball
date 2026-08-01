"""Regression coverage for mlb_baseball.model.offense.compute_wrc_plus_live
(ADR-046's offense.py sibling of starter.py::compute_live). The
underlying wOBA computation is covered by test_model_offense.py; the
Retrosheet-based wRC+ formula itself is covered by test_model_wrc_plus.py
-- this focuses on compute_wrc_plus_live() reading from raw.mlb_playbyplay
and correctly gating on home_wrc_plus IS NULL.
"""

from decimal import Decimal

from mlb_baseball.model import features, offense


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


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.mlb_playbyplay")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_league_average_hitter_in_a_neutral_park_is_exactly_100(db_conn):
    # Same algebraic sanity check as the Retrosheet-based version: if
    # team_woba equals league_woba (an exactly-average hitter) and
    # park_factor is 100 (a neutral park), wRC+ must reduce to exactly
    # 100 -- required by wRC+'s own definition.
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
            "('MLB920001', '920001', 2026, '2026-04-01', %(atl)s, %(nya)s, 1, 1, 'regular'), "
            "('MLB920002', '920002', 2026, '2026-04-02', %(atl)s, %(nya)s, 1, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        # G1: both sides bat identically -- team wOBA entering G2 will
        # equal league wOBA entering G2 exactly, by symmetry.
        cur.execute(
            "INSERT INTO raw.mlb_playbyplay "
            "(game_pk, at_bat_index, inning, half_inning, pitcher_id, event_type, outs, _season) "
            "VALUES "
            "('920001', '0', '1', 'bottom', '1', 'single', '0', '2026'), "
            "('920001', '1', '1', 'bottom', '1', 'field_out', '1', '2026'), "
            "('920001', '2', '1', 'top', '2', 'single', '0', '2026'), "
            "('920001', '3', '1', 'top', '2', 'field_out', '1', '2026'), "
            "('920002', '0', '1', 'bottom', '1', 'field_out', '1', '2026'), "
            "('920002', '1', '1', 'top', '2', 'field_out', '1', '2026')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    offense.compute_live(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature SET park_factor = 100 WHERE mlb_game_pk = '920002'"
        )
    db_conn.commit()
    offense.compute_wrc_plus_live(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_wrc_plus FROM gold.game_feature WHERE mlb_game_pk = '920002'"
        )
        (wrc_plus,) = cur.fetchone()

    assert wrc_plus == Decimal("100.00000000000000")

    _reset(db_conn)


def test_does_not_overwrite_retrosheet_derived_values(db_conn):
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
            "VALUES ('MLB920003', '920003', 2026, '2026-04-01', %(atl)s, %(nya)s, 5, 3, 'regular')",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()
    features.build(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature SET home_wrc_plus = 88.8 WHERE mlb_game_pk = '920003'"
        )
    db_conn.commit()

    offense.compute_wrc_plus_live(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT home_wrc_plus FROM gold.game_feature WHERE mlb_game_pk = '920003'")
        (wrc_plus,) = cur.fetchone()
    assert wrc_plus == Decimal("88.8")

    _reset(db_conn)


def test_returns_zero_without_playbyplay_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_playbyplay")
    db_conn.commit()

    assert offense.compute_wrc_plus_live(db_conn) == 0
