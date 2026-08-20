"""Regression coverage for mlb_baseball.model.experience -- starter career
experience entering a game (ADR-085, admission queue PLN-04's "prior MLB
PA/IP" half).
"""

from decimal import Decimal

import pytest

from mlb_baseball.model import experience, features


def _reset(db_conn):
    # DROPs (not DELETEs) every stub table this file creates on demand --
    # see test_model_team_rate.py's identical _reset for the full
    # explanation (issue #7/#9 item 5).
    db_conn.rollback()
    with db_conn.cursor() as cur:
        for table in ("raw.retrosheet_event", "raw.retrosheet_gameinfo"):
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


@pytest.fixture(autouse=True)
def _clean(db_conn):
    _reset(db_conn)
    yield
    _reset(db_conn)


def _ensure_retrosheet_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_event ("
                "game_id text, bat_home_id text, resp_pit_id text, "
                "resp_pit_start_fl text, bat_event_fl text, event_outs_ct text, "
                "_season text)"
            )
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_gameinfo ("
                "gid text, gametype text, visteam text, hometeam text, _season text)"
            )
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


def test_compute_carries_experience_across_season_boundaries(db_conn):
    # ATL (home) starter degrj001 starts G1 (2019) and G2 (2020, a
    # different season) -- career_bf/career_ip entering G2 must reflect
    # G1 alone, proving this window has NO season partition (unlike
    # starter.py's own season-scoped FIP/K%/BB%/HR% window). NYA (away)
    # starter cole0001 only appears in G2, so entering G2 his career
    # values are NULL (no prior appearance at all) -- both outcomes
    # checked in the same test.
    #
    # bat_home_id follows team_starter_retrosheet_update.sql's own
    # convention exactly: '0' = away team batting = HOME team's pitcher
    # is on the mound (resp_pit_id resolves the home starter); '1' = home
    # team batting = AWAY team's pitcher is on the mound.
    #
    # G1: degrj001 (home) faces 22 batters -- 18 rows record an out
    # (event_outs_ct='1', 18 outs = 6.0 IP) and 4 rows don't (a baserunner
    # reaching, event_outs_ct='0') -- BF = 18 + 4 = 22, outs = 18.
    _ensure_retrosheet_tables(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2019, '2019-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2020, '2020-04-01', %(atl)s, %(nya)s, 4, 2, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('G2', 'regular')"
        )
        rows = []
        # G1: home starter degrj001 -- 18 outs recorded, 4 batters reach.
        for _ in range(18):
            rows.append("('G1', '0', 'degrj001', 'T', 'T', '1', '2019')")
        for _ in range(4):
            rows.append("('G1', '0', 'degrj001', 'T', 'T', '0', '2019')")
        # G1: away starter oppop001 -- one minimal row, values unchecked.
        rows.append("('G1', '1', 'oppop001', 'T', 'T', '0', '2019')")
        # G2: home starter degrj001 again (entering-value check); away
        # starter cole0001 makes his first-ever appearance in this data.
        rows.append("('G2', '0', 'degrj001', 'T', 'T', '0', '2020')")
        rows.append("('G2', '1', 'cole0001', 'T', 'T', '0', '2020')")
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, resp_pit_id, resp_pit_start_fl, "
            "bat_event_fl, event_outs_ct, _season) VALUES " + ", ".join(rows)
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = experience.compute(db_conn)
    db_conn.commit()

    assert updated == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_starter_career_bf, f.home_starter_career_ip, "
            "f.away_starter_career_bf, f.away_starter_career_ip "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows_by_game = {r[0]: r[1:] for r in cur.fetchall()}

    assert rows_by_game["G1"] == (None, None, None, None)  # first appearance ever
    g2 = rows_by_game["G2"]
    assert g2[0] == 22  # home_starter_career_bf: G1's 22 BF carried forward
    assert g2[1] == Decimal("6.0")  # home_starter_career_ip: 18 outs / 3
    assert g2[2] is None  # away_starter_career_bf: cole0001's debut, no prior
    assert g2[3] is None  # away_starter_career_ip


def test_compute_returns_zero_without_retrosheet_event_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
    db_conn.commit()

    assert experience.compute(db_conn) == 0


def test_compute_returns_zero_without_retrosheet_gameinfo_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, bat_home_id text, resp_pit_id text, "
            "resp_pit_start_fl text, bat_event_fl text, event_outs_ct text, "
            "_season text)"
        )
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
    db_conn.commit()

    assert experience.compute(db_conn) == 0


def test_health_check_flags_an_implausible_value(db_conn):
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
            "UPDATE gold.game_feature SET home_starter_career_bf = 999999 "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G1')"
        )
    db_conn.commit()

    checks = experience.health_check()
    bf_check = next(c for c in checks if c.name == "home_starter_career_bf plausible range")

    assert not bf_check.ok
    assert "1 rows" in bf_check.detail
