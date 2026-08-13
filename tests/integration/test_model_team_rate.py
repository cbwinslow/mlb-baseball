"""Regression coverage for mlb_baseball.model.team_rate -- prior rolling
team OBP/SLG/ISO/BB%/K% (ADR-061, admission queue OFF-01/02/03) and prior
runs-for/allowed averages (OFF-08/DEF-01).
"""

from decimal import Decimal

from mlb_baseball.model import features, team_rate


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.retrosheet_event")
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.retrosheet_gameinfo")
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.mlb_schedule")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def _insert_three_games(db_conn):
    # ATL home in G1 (5-3 win) and G2 (2-6 loss); G3 is what we assert on.
    # Entering G3: runs_for_avg = (5+2)/2 = 3.5, runs_allowed_avg = (3+6)/2 = 4.5.
    with db_conn.cursor() as cur:
        # Ensure raw.mlb_schedule table exists with all needed columns
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.mlb_schedule (game_id text, game_datetime text, "
                "game_date text, game_type text, status text, home_id text, away_id text, "
                "game_num text, venue_id text, _season text, _loaded_at timestamptz)"
            )
        else:
            # Add missing columns if they don't exist
            cur.execute(
                "ALTER TABLE raw.mlb_schedule ADD COLUMN IF NOT EXISTS game_datetime text, "
                "ADD COLUMN IF NOT EXISTS _loaded_at timestamptz"
            )

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
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 1001, 2020, '2020-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 1002, 2020, '2020-04-08', %(atl)s, %(nya)s, 2, 6, 'regular'), "
            "('G3', 1003, 2020, '2020-04-15', %(atl)s, %(nya)s, 1, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        # Insert schedule records to trigger strict path in features.build()
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, game_datetime, game_date, game_type, status, home_id, away_id, "
            "game_num, _season, _loaded_at) "
            "VALUES "
            "('1001', '2020-04-01T18:00:00Z', '2020-04-01', 'R', 'Final', '144', '147', "
            "'1', '2020', now()), "
            "('1002', '2020-04-08T18:00:00Z', '2020-04-08', 'R', 'Final', '144', '147', "
            "'1', '2020', now()), "
            "('1003', '2020-04-15T18:00:00Z', '2020-04-15', 'R', 'Final', '144', '147', "
            "'1', '2020', now())"
        )
    db_conn.commit()


def test_compute_run_environment_matches_hand_calculation(db_conn):
    _reset(db_conn)
    _insert_three_games(db_conn)
    features.build(db_conn, strict=True)
    db_conn.commit()

    updated = team_rate.compute_run_environment(db_conn)
    db_conn.commit()

    assert updated == 3
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_runs_for_avg, f.home_runs_allowed_avg "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    assert rows["G1"] == (None, None)  # first game -- nothing prior
    assert rows["G3"] == (Decimal("3.5"), Decimal("4.5"))

    _reset(db_conn)


def test_compute_run_environment_is_idempotent(db_conn):
    _reset(db_conn)
    _insert_three_games(db_conn)
    features.build(db_conn, strict=True)
    db_conn.commit()

    team_rate.compute_run_environment(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_runs_for_avg FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id WHERE g.retro_game_id = 'G3'"
        )
        (first_run,) = cur.fetchone()

    team_rate.compute_run_environment(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_runs_for_avg FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id WHERE g.retro_game_id = 'G3'"
        )
        (second_run,) = cur.fetchone()

    assert first_run == second_run == Decimal("3.5")

    _reset(db_conn)


def _ensure_retrosheet_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_event ("
                "game_id text, bat_home_id text, event_cd text, "
                "ab_fl text, sf_fl text, bat_event_fl text, _season text)"
            )
        else:
            # A different test file may have created this table first with
            # an older, narrower column set -- add what this file needs
            # without disturbing whatever else already exists.
            cur.execute(
                "ALTER TABLE raw.retrosheet_event ADD COLUMN IF NOT EXISTS bat_event_fl text"
            )
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if not cur.fetchone()[0]:
            cur.execute("CREATE TABLE raw.retrosheet_gameinfo (gid text, gametype text)")
    db_conn.commit()


def test_compute_rolling_rate_stats_match_hand_calculation(db_conn):
    # ATL (home) in G1: 1 single, 1 double, 3 unintentional BB, 1
    # intentional BB, 1 HBP, 1 strikeout, 2 generic outs -- every one of
    # these is a real plate appearance, so bat_event_fl='T' on all of them
    # (see mlb_baseball/model/starter.py's module docstring, ADR-034: a
    # verified real-data reconciliation found bat_event_fl='T' is required
    # to correctly scope K/BB/HR counts from raw.retrosheet_event; the
    # extra row below proves this module now applies that same guard).
    #
    # Two extra unintentional-BB rows versus the original fixture (there
    # were 1 UBB + 1 IBB before) push PA from 8 to 10 -- this is
    # deliberate: PA=10 is exactly MIN_PA, so this test also proves the
    # gate is ">=" (inclusive), not strictly ">". AB is unaffected
    # by the extra walks (ab_fl='F' on every BB row), so AB stays at 5 --
    # below MIN_AB=8. SLG/ISO stay NULL for G2 because AB=5 is below the
    # MIN_AB=8 gate, even though OBP/BB%/K% (all gated on PA, not AB)
    # become real numbers -- the two gates are independent, and this
    # fixture happens to land on opposite sides of each one. The numbers
    # below are verified hand arithmetic, matching the module's own SQL.
    #   AB = single + double + 2 generic outs + strikeout = 5
    #      (ab_fl='T' on every batted/struck-out plate appearance below)
    #   H = 1B(1) + 2B(1) = 2; TB = 1*1 + 2*1 = 3
    #   BB = ubb(3) + ibb(1) = 4; HBP = 1; SF = 0; SO = 1
    #   PA = AB+BB+HBP+SF = 5+4+1+0 = 10  (>= MIN_PA=10 -> OBP/BB%/K% real)
    #   OBP = (H+BB+HBP)/PA = (2+4+1)/10 = 7/10 = 0.7
    #   BB% = BB/PA = 4/10 = 0.4; K% = SO/PA = 1/10 = 0.1
    #   AB = 5  (< MIN_AB=8 -> SLG/ISO gated to NULL, even though the raw
    #     hand-calculated SLG = TB/AB = 3/5 = 0.6 and ISO = SLG-AVG =
    #     0.6-0.4 = 0.2 are real, nonzero values -- the gate hides them
    #     for being too small a sample, same as OBP/BB%/K% would be
    #     hidden below MIN_PA)
    #
    # A tenth ATL row is a phantom event_cd='3' (strikeout-coded) record
    # with bat_event_fl='F' -- Retrosheet's own non-batter-event artifact
    # rows, not a real plate appearance. It must NOT move K% (or AB, since
    # ab_fl/sf_fl='F' on it too): if it did, K% would come out to 2/10=0.2
    # instead of the correct 1/10=0.1 asserted below.
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
            "(game_id, bat_home_id, event_cd, ab_fl, sf_fl, bat_event_fl, _season) VALUES "
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "  # single
            "('G1', '1', '21', 'T', 'F', 'T', '2020'), "  # double
            "('G1', '1', '14', 'F', 'F', 'T', '2020'), "  # unintentional BB
            "('G1', '1', '14', 'F', 'F', 'T', '2020'), "  # unintentional BB (extra, PA gate)
            "('G1', '1', '14', 'F', 'F', 'T', '2020'), "  # unintentional BB (extra, PA gate)
            "('G1', '1', '15', 'F', 'F', 'T', '2020'), "  # intentional BB
            "('G1', '1', '16', 'F', 'F', 'T', '2020'), "  # HBP
            "('G1', '1', '3',  'T', 'F', 'T', '2020'), "  # strikeout
            "('G1', '1', '3',  'F', 'F', 'F', '2020'), "  # phantom non-PA artifact row
            "('G1', '1', '2',  'T', 'F', 'T', '2020'), "  # generic out
            "('G1', '1', '2',  'T', 'F', 'T', '2020'), "  # generic out
            "('G1', '0', '2',  'T', 'F', 'T', '2020'), "  # NYA (away) -- minimal
            # G2 needs at least one event row per side for the rolling
            # window's "current row" to exist at all.
            "('G2', '1', '2', 'T', 'F', 'T', '2020'), "
            "('G2', '0', '2', 'T', 'F', 'T', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = team_rate.compute(db_conn)
    db_conn.commit()

    assert updated == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_obp, f.home_slg, f.home_iso, "
            "f.home_bb_pct, f.home_k_pct, f.home_pa, f.away_pa "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    assert rows["G1"] == (None, None, None, None, None, None, None)  # first game
    g2 = rows["G2"]
    assert g2[0] == Decimal("0.7")  # OBP  (PA=10 >= MIN_PA=10)
    assert g2[1] is None  # SLG  (AB=5 < MIN_AB=8 -- gated)
    assert g2[2] is None  # ISO  (AB=5 < MIN_AB=8 -- gated)
    assert g2[3] == Decimal("0.4")  # BB%  (PA=10 >= MIN_PA=10)
    assert g2[4] == Decimal("0.1")  # K%  (PA=10 >= MIN_PA=10)
    assert g2[5] == Decimal("10")  # home_pa  (ungated -- always populated)
    # NYA's only G1 row is a single generic out (ab_fl='T', event_cd='2',
    # not in the BB/HBP filter set): AB=1, BB=0, HBP=0, SF=0 ->
    # away_pa = AB+BB+HBP+SF = 1+0+0+0 = 1.
    assert g2[6] == Decimal("1")  # away_pa  (ungated -- always populated)

    _reset(db_conn)


def test_compute_gates_rate_stats_below_min_sample(db_conn):
    # ATL's only prior game (G1) has exactly 1 PA (a single, ab_fl='T',
    # bat_event_fl='T') -- 1 PA is below MIN_PA=10, so every PA-denominator
    # stat (OBP/BB%/K%) entering G2 must be NULL despite a real, nonzero
    # underlying value existing. PA itself is NOT gated -- it must still
    # report the real count (1) so a consumer can see why the rate is NULL.
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
            "(game_id, bat_home_id, event_cd, ab_fl, sf_fl, bat_event_fl, _season) VALUES "
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "  # ATL's only PA: 1 single
            "('G1', '0', '2',  'T', 'F', 'T', '2020'), "  # NYA -- minimal
            "('G2', '1', '2', 'T', 'F', 'T', '2020'), "
            "('G2', '0', '2', 'T', 'F', 'T', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    team_rate.compute(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT f.home_obp, f.home_bb_pct, f.home_k_pct, f.home_slg, f.home_iso, "
            "f.home_pa "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "WHERE g.retro_game_id = 'G2'"
        )
        row = cur.fetchone()

    assert row == (None, None, None, None, None, Decimal("1"))

    _reset(db_conn)


def test_compute_orders_doubleheader_by_game_number_not_insertion_order(db_conn):
    # Regression for a real ordering bug: the rolling window used to order
    # same-date rows by `game_id` (an insertion-order serial), not the
    # declared `game_number`, unlike the base family's own window
    # (mlb_baseball/sql/game_feature_rebuild.sql, migration 0046) which
    # orders by game_number specifically to stay correct regardless of
    # load order. A doubleheader loaded "second game first" (a realistic
    # cross-run backfill scenario) would then leak the second game's
    # stats into the first game's "entering" value, and vice versa.
    #
    # G1 (2020-04-01): ATL hits 8 singles -> AB=8, TB=8. (8, not 1, so
    # entering-DH1 AB clears MIN_AB=8 -- otherwise the min-sample gate
    # would gate SLG to NULL and this test couldn't observe the ordering
    # bug it's checking for at all. The 8-single/8-double counts below are
    # the original 1-single/1-double fixture scaled up by 8x, which keeps
    # the same SLG ratios -- 1.0/1.5 -- as the original, smaller fixture.)
    # Doubleheader on 2020-04-08, inserted DH2 (game_number=2) BEFORE DH1
    # (game_number=1) so DH2 gets the LOWER core.game.id despite being the
    # chronologically later game -- this is what would fool an
    # insertion-order sort.
    #   DH1 (game_number=1): ATL hits 8 doubles -> AB=8, TB=16.
    #   DH2 (game_number=2): ATL hits 1 triple -> AB=1, TB=3 (unused in
    #     assertions; only needs a row so the window has a "current row").
    #
    # Correctly ordered by game_number:
    #   entering DH1 = G1 only:      TB=8, AB=8, H=8 -> SLG = 1.0
    #   entering DH2 = G1 + DH1:     TB=8+16=24, AB=8+8=16, H=8+8=16 -> SLG = 1.5
    # If ordered by insertion order instead (the bug), DH2 (lower game_id)
    # would sort before DH1 on the same date, giving the wrong pairing:
    #   entering DH1 (buggy) = G1 + DH2 -> SLG = (8+3)/(8+1) = 11/9 = 1.222
    #   entering DH2 (buggy) = G1 only  -> SLG = 1.0
    #
    # ISO coverage (added after code review flagged that no test in this
    # file exercised a real, non-NULL ISO value once MIN_AB=8 landed --
    # the hand-calc test's own ISO went NULL under the gate, since that
    # test's AB stayed at 5). This fixture already clears AB>=8 at both
    # entering points, so it doubles as ISO coverage for free:
    #   AVG = H/AB; ISO = SLG - AVG
    #   entering DH1: AVG = 8/8 = 1.0 -> ISO = SLG-AVG = 1.0-1.0 = 0.0
    #     (all singles, so TB=H -- SLG and AVG coincide, a real edge case,
    #     not evidence of a broken computation)
    #   entering DH2: AVG = 16/16 = 1.0 -> ISO = 1.5-1.0 = 0.5
    #     (a real, nonzero value -- proves TB/AB - H/AB is actually
    #     subtracting two different numbers, not just echoing SLG)
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
            "(retro_game_id, season, game_date, game_number, home_team_id, "
            "away_team_id, home_score, away_score, game_type) VALUES "
            "('G1', 2020, '2020-04-01', 1, %(atl)s, %(nya)s, 5, 3, 'regular')",
            {"atl": atl, "nya": nya},
        )
        # DH2 (game_number=2) inserted before DH1 (game_number=1) on
        # purpose -- this is what gives DH2 the lower serial game_id.
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, game_number, home_team_id, "
            "away_team_id, home_score, away_score, game_type) VALUES "
            "('DH2', 2020, '2020-04-08', 2, %(atl)s, %(nya)s, 4, 2, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, game_number, home_team_id, "
            "away_team_id, home_score, away_score, game_type) VALUES "
            "('DH1', 2020, '2020-04-08', 1, %(atl)s, %(nya)s, 6, 5, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('DH1', 'regular'), ('DH2', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, event_cd, ab_fl, sf_fl, bat_event_fl, _season) VALUES "
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "  # ATL single (1/8)
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "  # ATL single (2/8)
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "  # ATL single (3/8)
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "  # ATL single (4/8)
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "  # ATL single (5/8)
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "  # ATL single (6/8)
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "  # ATL single (7/8)
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "  # ATL single (8/8)
            "('G1', '0', '2',  'T', 'F', 'T', '2020'), "  # NYA -- minimal
            "('DH1', '1', '21', 'T', 'F', 'T', '2020'), "  # ATL double (1/8)
            "('DH1', '1', '21', 'T', 'F', 'T', '2020'), "  # ATL double (2/8)
            "('DH1', '1', '21', 'T', 'F', 'T', '2020'), "  # ATL double (3/8)
            "('DH1', '1', '21', 'T', 'F', 'T', '2020'), "  # ATL double (4/8)
            "('DH1', '1', '21', 'T', 'F', 'T', '2020'), "  # ATL double (5/8)
            "('DH1', '1', '21', 'T', 'F', 'T', '2020'), "  # ATL double (6/8)
            "('DH1', '1', '21', 'T', 'F', 'T', '2020'), "  # ATL double (7/8)
            "('DH1', '1', '21', 'T', 'F', 'T', '2020'), "  # ATL double (8/8)
            "('DH1', '0', '2',  'T', 'F', 'T', '2020'), "  # NYA -- minimal
            "('DH2', '1', '22', 'T', 'F', 'T', '2020'), "  # ATL triple
            "('DH2', '0', '2',  'T', 'F', 'T', '2020')"  # NYA -- minimal
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = team_rate.compute(db_conn)
    db_conn.commit()

    assert updated == 3
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_slg, f.home_iso "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    assert rows["DH1"] == (Decimal("1.0"), Decimal("0.0"))  # SLG, ISO
    assert rows["DH2"] == (Decimal("1.5"), Decimal("0.5"))  # SLG, ISO

    _reset(db_conn)


def test_compute_returns_zero_without_retrosheet_event_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
    db_conn.commit()

    assert team_rate.compute(db_conn) == 0


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
            "UPDATE gold.game_feature SET home_obp = 5.0 "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G1')"
        )
    db_conn.commit()

    checks = team_rate.health_check()
    obp_check = next(c for c in checks if "obp" in c.name)

    assert not obp_check.ok
    assert "1 rows" in obp_check.detail

    _reset(db_conn)


def test_health_check_flags_a_min_sample_gate_violation(db_conn):
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
        # A populated home_obp with home_pa=5 violates the min-sample gate's
        # own contract (ADR-062: a populated OBP always had >= MIN_PA=10
        # prior PA) -- this simulates the gate silently ceasing to apply
        # (e.g. a future refactor reintroducing a bare `> 0` guard), which
        # only a real-data check like this one, not the fixture tests
        # above, can catch.
        cur.execute(
            "UPDATE gold.game_feature SET home_obp = 0.7, home_pa = 5 "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G1')"
        )
    db_conn.commit()

    checks = team_rate.health_check()
    gate_check = next(c for c in checks if "gate" in c.name)

    assert not gate_check.ok
    assert "1 rows" in gate_check.detail

    _reset(db_conn)


def test_compute_run_environment_unaffected_by_postponed_observation(db_conn):
    # A postponed schedule observation for a game_id never produces its own
    # core.game row (docs/GAME_INSTANCE_IDENTITY.md; only the real makeup
    # date's Final observation does) -- this proves compute_run_environment()
    # stays correct through that, since it only reads gold.game_feature's
    # own already-computed wins/losses/runs sums (mlb_baseball/sql/
    # game_feature_rebuild.sql, migration 0046), which already handle this.
    #
    # G1 (2020-04-01): ATL scores 5, allows 3.
    # A postponed observation for a game originally scheduled 2020-04-05
    # (never played that day -- no core.game row for it at all) sits in
    # raw.mlb_schedule alongside a *different*, later real game.
    # DH1 (game_number=1, 2020-04-08): ATL scores 6, allows 5.
    # DH2 (game_number=2, 2020-04-08, the actual makeup game, inserted
    #   before DH1 to also prove doubleheader game_number ordering holds
    #   for this function's pass-through): ATL scores 4, allows 2.
    #
    # Entering DH2: runs_for_avg = (5+6)/2 = 5.5, runs_allowed_avg = (3+5)/2 = 4.0
    # (must reflect G1+DH1 only -- the postponed observation contributes
    # nothing, and DH2 must not include itself).
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.mlb_schedule (game_id text, game_datetime text, "
                "game_date text, game_type text, status text, home_id text, away_id text, "
                "game_num text, venue_id text, _season text, _loaded_at timestamptz)"
            )
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
            "(retro_game_id, game_pk, season, game_date, game_number, "
            "home_team_id, away_team_id, home_score, away_score, game_type) VALUES "
            "('G1', 2001, 2020, '2020-04-01', 1, %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('DH2', 2003, 2020, '2020-04-08', 2, %(atl)s, %(nya)s, 4, 2, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, game_number, "
            "home_team_id, away_team_id, home_score, away_score, game_type) VALUES "
            "('DH1', 2002, 2020, '2020-04-08', 1, %(atl)s, %(nya)s, 6, 5, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, game_datetime, game_date, game_type, status, home_id, away_id, "
            "game_num, _season, _loaded_at) VALUES "
            "('2001', '2020-04-01T18:00:00Z', '2020-04-01', 'R', 'Final', "
            "'144', '147', '1', '2020', now()), "
            "('2002', '2020-04-08T17:00:00Z', '2020-04-08', 'R', 'Final', "
            "'144', '147', '1', '2020', now()), "
            "('2003', '2020-04-08T20:00:00Z', '2020-04-08', 'R', 'Final', "
            "'144', '147', '2', '2020', now()), "
            # Postponed-only observation: a game_id that never gets a
            # matching core.game row at all.
            "('2099', '2020-04-05T18:00:00Z', '2020-04-05', 'R', 'Postponed', "
            "'144', '147', '1', '2020', now())"
        )
    db_conn.commit()

    features.build(db_conn, strict=True)
    db_conn.commit()
    team_rate.compute_run_environment(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT f.home_runs_for_avg, f.home_runs_allowed_avg "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "WHERE g.retro_game_id = 'DH2'"
        )
        row = cur.fetchone()

    assert row == (Decimal("5.5"), Decimal("4.0"))

    _reset(db_conn)
