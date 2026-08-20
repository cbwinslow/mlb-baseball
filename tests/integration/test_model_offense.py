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
                "ab_fl text, sf_fl text, bat_event_fl text, _season text)"
            )
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if not cur.fetchone()[0]:
            cur.execute("CREATE TABLE raw.retrosheet_gameinfo (gid text, gametype text)")
    db_conn.commit()


def _reset(db_conn):
    # DROPs raw.retrosheet_event/retrosheet_gameinfo rather than DELETEing
    # their rows (issue #7): several test_model_*.py files each create their
    # own minimal stub schema for these two tables on demand, and a stub
    # with the wrong columns left behind by whichever file's tests happened
    # to run first in a full-suite session breaks every other file's own
    # schema expectations (or trips the real retrosheet connector's schema-
    # drift check when the full-column suite runs later in the same
    # session). Dropping means _ensure_retrosheet_tables always recreates
    # exactly this file's own shape, regardless of run order.
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
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
            "(game_id, bat_home_id, event_cd, ab_fl, sf_fl, bat_event_fl, _season) VALUES "
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "  # single
            "('G1', '1', '14', 'F', 'F', 'T', '2020'), "  # BB
            "('G1', '1', '16', 'F', 'F', 'T', '2020'), "  # HBP
            "('G1', '1', '2', 'T', 'F', 'T', '2020'), "  # generic out
            "('G1', '0', '2', 'T', 'F', 'T', '2020'), "  # NYA (away) batting -- minimal
            # G2 needs at least one event row per side for the rolling
            # window's "current row" to exist at all -- otherwise there's
            # nothing for the window to attach the entering-G2 value to.
            "('G2', '1', '2', 'T', 'F', 'T', '2020'), "
            "('G2', '0', '2', 'T', 'F', 'T', '2020')"
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


def test_compute_ignores_a_non_batter_event_phantom_row(db_conn):
    # Issue #9 item 6: team_woba_retrosheet_update.sql predates ADR-034's
    # finding (team_rate_retrosheet_update.sql's db97d96 fix) that every
    # event_cd count must be gated on bat_event_fl='T' -- without it, a
    # non-batter-event row (e.g. a baserunning-only pickoff/wild-pitch
    # artifact Retrosheet's own event files carry) with a coincidentally
    # matching event_cd would be double-counted into the wOBA numerator.
    # G1 has one real single (bat_event_fl='T') plus one phantom row with
    # event_cd='20' (single) but bat_event_fl='F' -- a real event_cd that
    # must NOT count, since it isn't a real plate appearance.
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
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "  # real single (1/1)
            "('G1', '1', '20', 'F', 'F', 'F', '2020'), "  # phantom -- must not count
            "('G1', '0', '2', 'T', 'F', 'T', '2020'), "  # NYA (away) batting -- minimal
            "('G2', '1', '2', 'T', 'F', 'T', '2020'), "
            "('G2', '0', '2', 'T', 'F', 'T', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = offense.compute(db_conn)
    db_conn.commit()

    assert updated == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT f.home_woba FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id WHERE g.retro_game_id = 'G2'"
        )
        (woba,) = cur.fetchone()

    # Entering G2 with the phantom row correctly excluded: 1 single only,
    # AB=1 -> wOBA = W_1B(0.878)/1 = 0.878. If the phantom row were wrongly
    # counted, AB would still be 1 (ab_fl='F' on the phantom, so AB itself
    # is unaffected) but the single-weighted numerator would double to
    # 1.756, giving wOBA = 1.756 -- a value clearly outside a real wOBA's
    # range, which is what this assertion actually rules out.
    assert woba == Decimal("0.8780")

    _reset(db_conn)


def test_compute_orders_doubleheader_by_game_number_not_insertion_order(db_conn):
    # Issue #9 item 6 (found by direct audit, same bug class as item 1's
    # db97d96 fix): the rolling window used to order same-date rows by
    # `game_id` (an insertion-order serial), not the declared
    # `game_number`. A doubleheader loaded "second game first" (a
    # realistic cross-run backfill scenario) would leak the second game's
    # stats into the first game's "entering" value, and vice versa.
    #
    # DH2 (game_number=2) is inserted BEFORE DH1 (game_number=1) so DH2
    # gets the LOWER core.game.id despite being the chronologically later
    # game -- this is what would fool an insertion-order sort.
    #   G1 (2020-04-01): ATL hits 1 single -> entering DH1 wOBA = 0.878/1.
    #   DH1 (game_number=1): ATL hits 1 double.
    #   DH2 (game_number=2): ATL hits 1 triple -- only needs a row so the
    #     window has a "current row"; unused in assertions.
    # Correctly ordered by game_number, entering DH2 = G1 + DH1:
    #   numerator = W_1B(0.878) + W_2B(1.242) = 2.120; AB=2 -> 1.060.
    # If ordered by insertion order instead (the bug), DH2 (lower game_id)
    # would sort before DH1 on the same date, so entering DH2 would only
    # see G1 (0.878), not G1+DH1 (1.060).
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
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "  # ATL single
            "('G1', '0', '2', 'T', 'F', 'T', '2020'), "  # NYA -- minimal
            "('DH1', '1', '21', 'T', 'F', 'T', '2020'), "  # ATL double
            "('DH1', '0', '2', 'T', 'F', 'T', '2020'), "  # NYA -- minimal
            "('DH2', '1', '22', 'T', 'F', 'T', '2020'), "  # ATL triple
            "('DH2', '0', '2', 'T', 'F', 'T', '2020')"  # NYA -- minimal
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = offense.compute(db_conn)
    db_conn.commit()

    assert updated == 3
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_woba "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1] for r in cur.fetchall()}

    assert abs(rows["DH2"] - Decimal("1.060")) < Decimal("0.0001")

    _reset(db_conn)


def test_compute_orders_doubleheader_by_coalesced_game_number_when_number_is_null(db_conn):
    # Issue #28: confirmed against real production `mlb` data that
    # Retrosheet's raw `number` field is genuinely empty for 10,020 games
    # (all 1901-1909), which conform.py turns into a NULL core.game.
    # game_number. `game_number NULLS LAST` sorts a NULL-game_number row
    # *after* any row with a real number -- wrong whenever the NULL game
    # is actually the earlier of a doubleheader pair. Same shape as
    # test_compute_orders_doubleheader_by_game_number_not_insertion_order
    # above but for the NULL-number case specifically (natural insertion
    # order alone doesn't trigger this bug -- `NULLS LAST` does, regardless
    # of game_id order).
    #   G1 (2020-04-01): ATL hits 1 single -> entering DH1 wOBA = 0.878/1.
    #   DH1 (game_number=NULL): ATL hits 1 double.
    #   DH2 (game_number=2): ATL hits 1 triple -- only needs a row so the
    #     window has a "current row"; unused in assertions.
    # Correctly ordered (COALESCE(game_number, 0) puts DH1 first), entering
    # DH2 = G1 + DH1: numerator = W_1B(0.878) + W_2B(1.242) = 2.120;
    # AB=2 -> 1.060. If ordered by `game_number NULLS LAST` instead (the
    # bug), DH2 (non-null) sorts before DH1 (NULL) despite being the later
    # game, so entering DH2 would only see G1 (0.878), not G1+DH1 (1.060).
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
        # DH1's game_number is NULL -- the malformed-source-data case.
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, game_number, home_team_id, "
            "away_team_id, home_score, away_score, game_type) VALUES "
            "('DH1', 2020, '2020-04-08', NULL, %(atl)s, %(nya)s, 6, 5, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, game_number, home_team_id, "
            "away_team_id, home_score, away_score, game_type) VALUES "
            "('DH2', 2020, '2020-04-08', 2, %(atl)s, %(nya)s, 4, 2, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('DH1', 'regular'), ('DH2', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, event_cd, ab_fl, sf_fl, bat_event_fl, _season) VALUES "
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "  # ATL single
            "('G1', '0', '2', 'T', 'F', 'T', '2020'), "  # NYA -- minimal
            "('DH1', '1', '21', 'T', 'F', 'T', '2020'), "  # ATL double
            "('DH1', '0', '2', 'T', 'F', 'T', '2020'), "  # NYA -- minimal
            "('DH2', '1', '22', 'T', 'F', 'T', '2020'), "  # ATL triple
            "('DH2', '0', '2', 'T', 'F', 'T', '2020')"  # NYA -- minimal
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = offense.compute(db_conn)
    db_conn.commit()

    assert updated == 3
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_woba "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1] for r in cur.fetchall()}

    assert abs(rows["DH2"] - Decimal("1.060")) < Decimal("0.0001")

    _reset(db_conn)


def test_compute_returns_zero_without_retrosheet_event_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
    db_conn.commit()

    assert offense.compute(db_conn) == 0

    _reset(db_conn)


def test_compute_returns_zero_without_retrosheet_gameinfo_table(db_conn):
    # Issue #9 item 2: compute()'s own SQL joins raw.retrosheet_gameinfo
    # too, but only retrosheet_event was gated -- retrosheet_event and
    # retrosheet_gameinfo are landed by two different connectors
    # (retrosheet_event.py, retrosheet.py), so a fresh clone that's only
    # bootstrapped one of them previously hit an UndefinedTable error here
    # instead of the same clean "not ready yet" 0 every sibling gate gives.
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, bat_home_id text, event_cd text, "
            "ab_fl text, sf_fl text, _season text)"
        )
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
    db_conn.commit()

    assert offense.compute(db_conn) == 0

    _reset(db_conn)


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
        cur.execute("UPDATE gold.game_feature SET home_woba = 0.333 WHERE mlb_game_pk = '910003'")
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


def test_health_check_accepts_verified_small_sample_historical_extreme(db_conn):
    # Real production value, not synthetic: the Philadelphia Stars (retro_team_id
    # PH5, Negro League, 1934-1949) entering their 1946-05-13 home game had
    # exactly one prior 1946 game with Retrosheet play-by-play coverage, going
    # 0-for-56 with 2 walks. Hand-verified against production on 2026-08-14:
    # wOBA = (0.690*2) / (56+2) = 0.023793103448275862... -- see offense.py's
    # health_check docstring. Not a bug; a genuine computation bug (e.g. a
    # dropped weight or inverted denominator) would produce something well
    # outside even this widened bound, which the previous test covers.
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
            "UPDATE gold.game_feature SET home_woba = 0.0237931034482759 "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G1')"
        )
    db_conn.commit()

    check = offense.health_check()[0]

    assert check.ok

    _reset(db_conn)


def test_health_check_flags_a_woba_coverage_gap(db_conn):
    # Issue #32: the plausible-range check above can only ever catch a
    # value that's present but out of range -- a total join failure (e.g. a
    # mismatched team_id in team_woba_retrosheet_update.sql) makes the
    # column NULL for every row instead, which the range check's own
    # `IS NOT NULL` filter explicitly excludes from the count. ATL is
    # "eligible" entering G2 (it has a real, covered prior game, G1) so a
    # NULL home_woba there is exactly the silent-join-break scenario the
    # coverage check exists to catch -- not the ordinary "first game of the
    # season, nothing prior yet" NULL that G1 itself would still have if
    # its own home_woba were (correctly) NULL.
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
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "  # ATL single
            "('G1', '0', '2', 'T', 'F', 'T', '2020'), "  # NYA (away) -- minimal
            "('G2', '1', '2', 'T', 'F', 'T', '2020'), "
            "('G2', '0', '2', 'T', 'F', 'T', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    offense.compute(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT f.home_woba FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id WHERE g.retro_game_id = 'G2'"
        )
        (woba,) = cur.fetchone()
    assert woba is not None  # sanity: compute() really did populate it

    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature SET home_woba = NULL "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G2')"
        )
    db_conn.commit()

    checks = offense.health_check()
    coverage_check = next(c for c in checks if c.name == "home_woba coverage")

    assert not coverage_check.ok
    assert "1 eligible rows" in coverage_check.detail

    _reset(db_conn)


def test_health_check_flags_a_wrc_plus_coverage_gap(db_conn):
    # Issue #32, home_wrc_plus/away_wrc_plus half: these have no separate
    # per-side join to break (both are computed straight off
    # home_woba/park_factor in the same UPDATE, see
    # team_wrc_plus_retrosheet_update.sql), so their coverage check is
    # simpler -- once woba and park_factor are both present, wrc_plus must
    # be too. This simulates that UPDATE simply not having run yet on one
    # row despite its inputs being ready. Needs the retrosheet tables to
    # exist even though this check's own query never reads them -- both
    # coverage sub-checks share one gate (offense.py::health_check), since
    # wrc_plus is never meaningful before woba/park_factor are, which in
    # practice always requires retrosheet coverage anyway.
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
            "home_score, away_score, game_type) "
            "VALUES ('G1', 2024, '2024-04-01', %s, %s, 5, 3, 'regular')",
            (atl, nya),
        )
    db_conn.commit()
    features.build(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature SET home_woba = 0.320, park_factor = 100, "
            "home_wrc_plus = NULL "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G1')"
        )
    db_conn.commit()

    checks = offense.health_check()
    coverage_check = next(c for c in checks if c.name == "home_wrc_plus coverage")

    assert not coverage_check.ok
    # Not "eligible" -- G1 is this team's first game of the season, so it
    # never clears the row_number() > 1 eligibility bar the woba/pa checks
    # use. wrc_plus coverage checks a different, simpler population
    # (woba/park_factor already present), and the message says so
    # explicitly (PR #54 review: this assertion used to say "eligible",
    # which only passed because the SQL never actually applied that
    # criterion to wrc_plus -- true by accident, not by the check's design).
    assert "1 woba/park_factor-populated rows" in coverage_check.detail

    _reset(db_conn)
