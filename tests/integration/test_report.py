"""Regression coverage for mlb_baseball.report -- the gold-layer reporting
surface (ADR-057): gold.player_season, gold.team_season,
gold.division_standing.

raw.bref_batting/raw.bref_pitching/raw.lahman_teams/raw.mlb_standing are
dynamically created by load_dataframe in production (see mlb_baseball/
load.py), not migrations, so this file creates them itself, matching
test_model_offense.py's own convention for raw.retrosheet_event/
raw.retrosheet_gameinfo. Every hand-computed expected value in this file is
worked out in the comment right above the assertion it belongs to -- same
discipline as test_model_offense.py/test_model_war.py.
"""

from decimal import Decimal

import pytest

from mlb_baseball import report

_DYNAMIC_RAW_TABLES = [
    "raw.bref_batting",
    "raw.bref_pitching",
    "raw.lahman_teams",
    "raw.mlb_standing",
    "raw.retrosheet_event",
    "raw.retrosheet_gameinfo",
]


def _ensure_dynamic_tables(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.bref_batting')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.bref_batting (name text, tm text, g text, pa text, ab text, "
                "r text, h text, n2b text, n3b text, hr text, rbi text, bb text, so text, "
                "hbp text, sb text, cs text, ba text, obp text, slg text, ops text, "
                "mlbid text, _season text)"
            )
        cur.execute("SELECT to_regclass('raw.bref_pitching')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.bref_pitching (name text, tm text, g text, gs text, w text, "
                "l text, sv text, ip text, h text, r text, er text, bb text, so text, hr text, "
                "era text, whip text, so9 text, mlbid text, _season text)"
            )
        cur.execute("SELECT to_regclass('raw.lahman_teams')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.lahman_teams (yearid text, lgid text, teamidretro text, "
                "w text, l text, r text, ra text, hr text, era text)"
            )
        cur.execute("SELECT to_regclass('raw.mlb_standing')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.mlb_standing (team_id text, _season text, elim_num text, "
                "wc_elim_num text)"
            )
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_event (game_id text, bat_home_id text, "
                "event_cd text, ab_fl text, sf_fl text, _season text)"
            )
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if not cur.fetchone()[0]:
            cur.execute("CREATE TABLE raw.retrosheet_gameinfo (gid text, gametype text)")
    conn.commit()


def _reset(conn):
    conn.rollback()
    with conn.cursor() as cur:
        for table in _DYNAMIC_RAW_TABLES:
            cur.execute(f"SELECT to_regclass('{table}')")
            if cur.fetchone()[0]:
                cur.execute(f"DELETE FROM {table}")
        for table in (
            "gold.player_season",
            "gold.team_season",
            "gold.division_standing",
            "core.standing",
            "core.player_war",
            "core.game",
            "core.player",
            "core.team",
            "core.venue",
        ):
            cur.execute(f"DELETE FROM {table}")
    conn.commit()


def _insert_teams(cur, rows):
    """rows: list of (retro_team_id, city, nickname, first_year, last_year, mlb_team_id)."""
    ids = {}
    for retro_id, city, nickname, first_year, last_year, mlb_id in rows:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (retro_id, city, nickname, first_year, last_year, mlb_id),
        )
        ids[retro_id] = cur.fetchone()[0]
    return ids


# ---------------------------------------------------------------------------
# gold.player_season
# ---------------------------------------------------------------------------


def test_build_player_season_resolves_batting_and_pitching_and_sums_war(db_conn):
    _reset(db_conn)
    _ensure_dynamic_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.player (retro_id, mlbam_id, first_name, last_name) "
            "VALUES ('battera01', '660271', 'Bat', 'Ter') RETURNING id"
        )
        (batter_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO core.player (retro_id, mlbam_id, first_name, last_name) "
            "VALUES ('pitchea01', '592789', 'Pitch', 'Er') RETURNING id"
        )
        (pitcher_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO raw.bref_batting "
            "(name, tm, g, pa, ab, r, h, n2b, n3b, hr, rbi, bb, so, hbp, sb, cs, "
            "ba, obp, slg, ops, mlbid, _season) VALUES "
            "('Bat Ter', 'Los Angeles', '150', '600', '540', '80', '150', '30', '2', "
            "'20', '75', '50', '110', '5', '15', '4', '0.278', '0.345', '0.460', "
            "'0.805', '660271', '2023')"
        )
        cur.execute(
            "INSERT INTO raw.bref_pitching "
            "(name, tm, g, gs, w, l, sv, ip, h, r, er, bb, so, hr, era, whip, so9, "
            "mlbid, _season) VALUES "
            "('Pitch Er', 'New York', '30', '30', '12', '8', '', '180.1', '160', "
            "'70', '65', '45', '190', '18', '3.25', '1.137', '9.5', '592789', '2023')"
        )
        # Two stints (traded mid-season) -- must be summed, matching
        # core.player_war's own real grain (confirmed against production,
        # see report.py's own docstring).
        cur.execute(
            "INSERT INTO core.player_war (player_id, season, is_pitcher, team_code, war, waa) "
            "VALUES (%s, 2023, false, 'LAD', 2.5, 1.1), (%s, 2023, false, 'NYY', 1.0, 0.4), "
            "(%s, 2023, true, 'NYY', 4.2, 2.0)",
            (batter_id, batter_id, pitcher_id),
        )
    db_conn.commit()

    counts = {
        "gold.player_season": report._build_player_season(db_conn),
    }
    db_conn.commit()

    assert counts["gold.player_season"] == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT is_pitcher, games, pa, ab, doubles, triples, hr, rbi, bb, so, hbp, "
            "sb, cs, avg, obp, slg, ops, war, waa "
            "FROM gold.player_season WHERE player_id = %s",
            (batter_id,),
        )
        row = cur.fetchone()
        assert row == (
            False, 150, 600, 540, 30, 2, 20, 75, 50, 110, 5, 15, 4,
            Decimal("0.278"), Decimal("0.345"), Decimal("0.460"), Decimal("0.805"),
            Decimal("3.5"),  # 2.5 + 1.0, summed across both 2023 stints
            Decimal("1.5"),  # 1.1 + 0.4
        )
        cur.execute(
            "SELECT is_pitcher, games, gs, w, l, sv, ip, er, era, whip, so9, "
            "r, h, bb, so, hr, war, waa "
            "FROM gold.player_season WHERE player_id = %s",
            (pitcher_id,),
        )
        row = cur.fetchone()
        assert row == (
            True, 30, 30, 12, 8, None, Decimal("180.1"), 65,
            Decimal("3.25"), Decimal("1.137"), Decimal("9.5"),
            70, 160, 45, 190, 18, Decimal("4.2"), Decimal("2.0"),
        )

    _reset(db_conn)


def test_build_player_season_excludes_rows_with_no_resolvable_player(db_conn):
    # A real, documented gap (~0.5% of production rows, see ADR-057) --
    # confirmed excluded, not silently turned into a NULL-player_id row
    # (player_id is NOT NULL on gold.player_season -- see migration 0030).
    _reset(db_conn)
    _ensure_dynamic_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.bref_batting "
            "(name, tm, g, pa, ab, r, h, n2b, n3b, hr, rbi, bb, so, hbp, sb, cs, "
            "ba, obp, slg, ops, mlbid, _season) VALUES "
            "('Unknown Guy', 'Boston', '10', '20', '18', '2', '4', '1', '0', '0', "
            "'2', '2', '4', '0', '0', '0', '0.222', '0.300', '0.278', '0.578', "
            "'999999999', '2023')"
        )
    db_conn.commit()

    updated = report._build_player_season(db_conn)
    db_conn.commit()

    assert updated == 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.player_season")
        assert cur.fetchone() == (0,)

    _reset(db_conn)


# ---------------------------------------------------------------------------
# gold.team_season
# ---------------------------------------------------------------------------


def test_build_team_season_base_from_lahman_computes_win_pct_and_remaps_athletics(db_conn):
    # 'ATH' (the Athletics' bare 2025 post-relocation code -- same gap
    # conform.py's own _TEAM_ALIAS_SEED documents for Kalshi/Polymarket)
    # must resolve via core.team's real 'OAK' retro_team_id, not silently
    # drop the row.
    _reset(db_conn)
    _ensure_dynamic_tables(db_conn)
    with db_conn.cursor() as cur:
        teams = _insert_teams(
            cur,
            [
                ("LAN", "Los Angeles", "Dodgers", 1958, 9999, 119),
                ("OAK", "Oakland", "Athletics", 1968, 9999, 133),
            ],
        )
        cur.execute(
            "INSERT INTO raw.lahman_teams (yearid, lgid, teamidretro, w, l, r, ra, hr, era) "
            "VALUES "
            "('2024', 'NL', 'LAN', '98', '64', '842', '659', '210', '3.71'), "
            "('2025', 'AL', 'ATH', '76', '86', '733', '744', '219', '4.71')"
        )
    db_conn.commit()

    updated = report._build_team_season_base(db_conn)
    db_conn.commit()

    assert updated == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT team_id, wins, losses, win_pct, runs, runs_allowed, hr, era "
            "FROM gold.team_season WHERE season = 2024"
        )
        row = cur.fetchone()
        # win_pct = 98 / (98+64) = 0.60494, rounded to 3 places = 0.605
        assert row == (teams["LAN"], 98, 64, Decimal("0.605"), 842, 659, 210, Decimal("3.71"))
        cur.execute(
            "SELECT team_id, wins, losses FROM gold.team_season WHERE season = 2025"
        )
        assert cur.fetchone() == (teams["OAK"], 76, 86)

    _reset(db_conn)


def test_compute_park_factor_matches_hand_calculation(db_conn):
    # Team A home games (season 2023): (5+3)=8, (5+3)=8 -> home_rate=8
    # Team A road games (season 2023): (6+4)=10, (6+4)=10 -> road_rate=10
    # park_factor(Team A, target season 2024) = 100 * 8/10 = 80 (exact)
    _reset(db_conn)
    _ensure_dynamic_tables(db_conn)
    with db_conn.cursor() as cur:
        teams = _insert_teams(
            cur,
            [
                ("TMA", "Aville", "Aces", 1960, 9999, 900),
                ("TMB", "Bville", "Bears", 1960, 9999, 901),
            ],
        )
        team_a, team_b = teams["TMA"], teams["TMB"]
        cur.execute(
            "INSERT INTO core.venue (retro_park_id, name) VALUES ('AVI01', 'Aville Park') "
            "RETURNING id"
        )
        (venue_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type, venue_id) VALUES "
            "('PF1', 2023, '2023-04-01', %(a)s, %(b)s, 5, 3, 'regular', %(v)s), "
            "('PF2', 2023, '2023-04-08', %(a)s, %(b)s, 5, 3, 'regular', %(v)s), "
            "('PF3', 2023, '2023-04-15', %(b)s, %(a)s, 6, 4, 'regular', %(v)s), "
            "('PF4', 2023, '2023-04-22', %(b)s, %(a)s, 6, 4, 'regular', %(v)s)",
            {"a": team_a, "b": team_b, "v": venue_id},
        )
        # gold.team_season row must already exist for the target season --
        # _compute_park_factor only fills park_factor onto rows the base
        # INSERT (raw.lahman_teams) already established (see run()'s own
        # ordering comment).
        cur.execute(
            "INSERT INTO gold.team_season (team_id, season) VALUES (%s, 2024)", (team_a,)
        )
    db_conn.commit()

    updated = report._compute_park_factor(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT park_factor FROM gold.team_season WHERE team_id = %s AND season = 2024",
            (team_a,),
        )
        (park_factor,) = cur.fetchone()
    assert park_factor == pytest.approx(Decimal("80"), rel=Decimal("0.0001"))

    _reset(db_conn)


def test_compute_woba_and_wrc_plus_matches_hand_calculation(db_conn):
    # Team A (home, bat_home_id='1'): exactly 1 plate appearance, a single
    # (ab=1, b1=1, everything else 0).
    #   wOBA(A) = 0.878*1 / 1 = 0.878 (exact)
    # Team B (away, bat_home_id='0'): exactly 1 plate appearance, a home run.
    #   wOBA(B) = 2.015*1 / 1 = 2.015 (exact)
    # League (both teams combined, season 2024, only this one game):
    #   (0.878 + 2.015) / 2 = 2.893 / 2 = 1.4465 (exact)
    # park_factor preset to 100 on both rows (isolates this test from
    # _compute_park_factor, matching this project's own "one function's
    # test doesn't also exercise a different function" convention -- see
    # e.g. test_model_war.py never touching offense.py).
    #   wrc_plus(A) = (((0.878-1.4465)/1.20)+1)*100 = (-0.47375+1)*100 = 52.625
    #   wrc_plus(B) = (((2.015-1.4465)/1.20)+1)*100 = (0.47375+1)*100 = 147.375
    _reset(db_conn)
    _ensure_dynamic_tables(db_conn)
    with db_conn.cursor() as cur:
        teams = _insert_teams(
            cur,
            [
                ("TMA", "Aville", "Aces", 1960, 9999, 900),
                ("TMB", "Bville", "Bears", 1960, 9999, 901),
            ],
        )
        team_a, team_b = teams["TMA"], teams["TMB"]
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('WB1', 2024, '2024-04-01', %(a)s, %(b)s, 4, 1, 'regular')",
            {"a": team_a, "b": team_b},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) VALUES ('WB1', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, event_cd, ab_fl, sf_fl, _season) "
            "VALUES "
            "('WB1', '1', '20', 'T', 'F', '2024'), "  # A: single
            "('WB1', '0', '23', 'T', 'F', '2024')"  # B: home run
        )
        cur.execute(
            "INSERT INTO gold.team_season (team_id, season, park_factor) VALUES "
            "(%s, 2024, 100), (%s, 2024, 100)",
            (team_a, team_b),
        )
    db_conn.commit()

    updated = report._compute_woba(db_conn)
    db_conn.commit()

    assert updated == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT woba, wrc_plus FROM gold.team_season WHERE team_id = %s AND season = 2024",
            (team_a,),
        )
        woba_a, wrc_a = cur.fetchone()
        cur.execute(
            "SELECT woba, wrc_plus FROM gold.team_season WHERE team_id = %s AND season = 2024",
            (team_b,),
        )
        woba_b, wrc_b = cur.fetchone()

    assert woba_a == pytest.approx(Decimal("0.878"), rel=Decimal("0.0001"))
    assert woba_b == pytest.approx(Decimal("2.015"), rel=Decimal("0.0001"))
    assert wrc_a == pytest.approx(Decimal("52.625"), rel=Decimal("0.0001"))
    assert wrc_b == pytest.approx(Decimal("147.375"), rel=Decimal("0.0001"))

    _reset(db_conn)


def test_compute_war_sums_across_batting_and_pitching_via_bref_crosswalk(db_conn):
    # core.player_war.team_code uses bref's own abbreviation (LAD), not
    # core.team.retro_team_id (LAN) -- same crosswalk gap war.py's own
    # module docstring documents; reused here, not duplicated.
    _reset(db_conn)
    _ensure_dynamic_tables(db_conn)
    with db_conn.cursor() as cur:
        teams = _insert_teams(cur, [("LAN", "Los Angeles", "Dodgers", 1958, 9999, 119)])
        lan = teams["LAN"]
        cur.execute(
            "INSERT INTO core.player (retro_id, first_name, last_name) "
            "VALUES ('playa001', 'A', 'One'), ('playb001', 'B', 'Two') RETURNING id"
        )
        players = [row[0] for row in cur.fetchall()]
        cur.execute(
            "INSERT INTO core.player_war (player_id, season, is_pitcher, team_code, war) VALUES "
            "(%s, 2023, false, 'LAD', 5.0), (%s, 2023, true, 'LAD', 3.5)",
            (players[0], players[1]),
        )
        cur.execute("INSERT INTO gold.team_season (team_id, season) VALUES (%s, 2023)", (lan,))
    db_conn.commit()

    updated = report._compute_war(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT war FROM gold.team_season WHERE team_id = %s AND season = 2023", (lan,)
        )
        (war,) = cur.fetchone()
    assert war == Decimal("8.5")

    _reset(db_conn)


# ---------------------------------------------------------------------------
# gold.division_standing
# ---------------------------------------------------------------------------


def test_build_division_standing_enriches_core_standing_with_elim_num(db_conn):
    _reset(db_conn)
    _ensure_dynamic_tables(db_conn)
    with db_conn.cursor() as cur:
        teams = _insert_teams(cur, [("NYA", "New York", "Yankees", 1913, 9999, 147)])
        nya = teams["NYA"]
        cur.execute(
            "INSERT INTO core.standing "
            "(team_id, season, division, div_rank, wins, losses, games_back, "
            "wildcard_rank, wildcard_games_back, league_rank, sport_rank) VALUES "
            "(%s, 2024, 'American League East', 2, 94, 68, 3.0, 4, 0.0, 3, 5)",
            (nya,),
        )
        cur.execute(
            "INSERT INTO raw.mlb_standing (team_id, _season, elim_num, wc_elim_num) "
            "VALUES ('147', '2024', '-', 'E')"
        )
    db_conn.commit()

    updated = report._build_division_standing(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT team_city, team_nickname, division, div_rank, wins, losses, win_pct, "
            "games_back, wildcard_rank, wildcard_games_back, league_rank, sport_rank, "
            "elim_num, wildcard_elim_num "
            "FROM gold.division_standing WHERE team_id = %s",
            (nya,),
        )
        row = cur.fetchone()
    # win_pct = 94 / (94+68) = 0.58024..., rounded to 3 places = 0.580
    assert row == (
        "New York", "Yankees", "American League East", 2, 94, 68, Decimal("0.580"),
        Decimal("3.0"), 4, Decimal("0.0"), 3, 5, "-", "E",
    )

    _reset(db_conn)


# ---------------------------------------------------------------------------
# run() / health_check()
# ---------------------------------------------------------------------------


def test_run_is_idempotent(db_conn):
    # CLAUDE.md's own definition of done: re-running must not duplicate or
    # corrupt data. run() does its own TRUNCATE + rebuild, so two
    # consecutive calls must land on the exact same row set, not double it.
    _reset(db_conn)
    _ensure_dynamic_tables(db_conn)
    with db_conn.cursor() as cur:
        teams = _insert_teams(cur, [("LAN", "Los Angeles", "Dodgers", 1958, 9999, 119)])
        lan = teams["LAN"]
        cur.execute(
            "INSERT INTO core.player (retro_id, mlbam_id, first_name, last_name) "
            "VALUES ('battera01', '660271', 'Bat', 'Ter') RETURNING id"
        )
        (batter_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO raw.bref_batting "
            "(name, tm, g, pa, ab, r, h, n2b, n3b, hr, rbi, bb, so, hbp, sb, cs, "
            "ba, obp, slg, ops, mlbid, _season) VALUES "
            "('Bat Ter', 'Los Angeles', '150', '600', '540', '80', '150', '30', '2', "
            "'20', '75', '50', '110', '5', '15', '4', '0.278', '0.345', '0.460', "
            "'0.805', '660271', '2023')"
        )
        cur.execute(
            "INSERT INTO raw.lahman_teams (yearid, lgid, teamidretro, w, l, r, ra, hr, era) "
            "VALUES ('2023', 'NL', 'LAN', '100', '62', '900', '700', '220', '3.50')"
        )
        cur.execute(
            "INSERT INTO core.standing "
            "(team_id, season, division, div_rank, wins, losses) VALUES "
            "(%s, 2023, 'National League West', 1, 100, 62)",
            (lan,),
        )
    db_conn.commit()

    first = report.run()
    second = report.run()

    assert first == second
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.player_season")
        assert cur.fetchone() == (1,)
        cur.execute("SELECT count(*) FROM gold.team_season")
        assert cur.fetchone() == (1,)
        cur.execute("SELECT count(*) FROM gold.division_standing")
        assert cur.fetchone() == (1,)

    _reset(db_conn)


def test_health_check_returns_checks_without_crashing(db_conn):
    _reset(db_conn)
    _ensure_dynamic_tables(db_conn)
    checks = report.health_check()
    assert len(checks) >= 5
    assert all(hasattr(c, "ok") for c in checks)
    _reset(db_conn)
