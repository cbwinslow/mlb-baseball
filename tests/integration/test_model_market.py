"""Regression coverage for mlb_baseball.model.market -- market-implied
win probability recorded as a comparison line against log5/elo/gbm's own
predictions (ADR-053).

core.market is seeded directly (a decided core.game row plus a matching
core.market row), not via the full conform.run() pipeline -- market.py
only ever reads core.market/core.game/raw.polymarket_market, all cheap
to seed directly here, same shortcut test_model_log5.py already takes
for core.game.
"""

from decimal import Decimal

from mlb_baseball.model import market


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


def _seed_decided_game(db_conn, atl, nya, game_pk="999001", retro_game_id="G1"):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) "
            "VALUES (%s, %s, 2024, '2024-04-01', %s, %s, 5, 3, 'regular') "
            "RETURNING id",
            (retro_game_id, game_pk, atl, nya),
        )
        (game_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(game_id, mlb_game_pk, game_instance_key, season, game_date, home_team_id, "
            "away_team_id, home_win) "
            "VALUES (%s, %s, %s, 2024, '2024-04-01', %s, %s, true)",
            (game_id, game_pk, f"test:market:{retro_game_id}", atl, nya),
        )
    return game_id


def _seed_market_row(db_conn, game_id, source, team_id, implied_probability, market_ref):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.market "
            "(game_id, source, market_ref, team_id, implied_probability, volume, status) "
            "VALUES (%s, %s, %s, %s, %s, 1000, 'closed')",
            (game_id, source, market_ref, team_id, implied_probability),
        )


def _ensure_polymarket_market_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.polymarket_market')")
        (exists,) = cur.fetchone()
        if not exists:
            cur.execute("CREATE TABLE raw.polymarket_market (id text, sportsmarkettype text)")
    db_conn.commit()


def _seed_polymarket_market_type(db_conn, market_id, sportsmarkettype):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.polymarket_market (id, sportsmarkettype) VALUES (%s, %s)",
            (market_id, sportsmarkettype),
        )


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        for table in (
            "raw.polymarket_outcome",
            "raw.polymarket_snapshot",
            "raw.polymarket_event",
            "raw.polymarket_market",
            "raw.kalshi_snapshot",
            "raw.kalshi_market",
        ):
            cur.execute("SELECT to_regclass(%s)", (table,))
            (exists,) = cur.fetchone()
            if exists:
                cur.execute(f"DELETE FROM {table}")
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        (schedule_exists,) = cur.fetchone()
        if schedule_exists:
            # Only the rows this file inserts. A full DELETE (or a skinny
            # CREATE TABLE IF NOT EXISTS) poisons later tests that call
            # features.build() — CI 2026-08-28: UndefinedColumn ms.home_id.
            cur.execute("DELETE FROM raw.mlb_schedule WHERE game_id LIKE '888%'")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.market")
        cur.execute("DELETE FROM core.game")
        cur.execute(
            "DELETE FROM core.team_alias a USING core.team t "
            "WHERE a.team_id = t.id AND t.retro_team_id IN ('ATL', 'NYA')"
        )
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_record_inserts_home_teams_moneyline_price_as_prediction(db_conn):
    _reset(db_conn)
    _ensure_polymarket_market_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    game_id = _seed_decided_game(db_conn, atl, nya)
    _seed_polymarket_market_type(db_conn, "m1", "moneyline")
    _seed_market_row(db_conn, game_id, "polymarket", atl, Decimal("0.62"), "m1:atl")
    db_conn.commit()

    inserted = market.record(db_conn)
    db_conn.commit()

    assert inserted == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT mlb_game_pk, model_version, home_win_prob, actual_home_win FROM gold.prediction"
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    mlb_game_pk, model_version, home_win_prob, actual = rows[0]
    assert mlb_game_pk == "999001"
    assert model_version == "polymarket-v1"
    assert home_win_prob == Decimal("0.62")
    assert actual is None  # backfill_outcomes() is a separate step, not record()'s job

    _reset(db_conn)


def test_record_ignores_non_moneyline_markets_for_the_same_game_and_team(db_conn):
    # Real bug found running this against production: a single Polymarket
    # event carries multiple distinct markets (moneyline, run-line spreads,
    # first-five-innings spreads) all resolving to the same (game, team)
    # match -- confirmed directly, PHI@BAL 2026-08-02 alone had 7 distinct
    # market_ids sharing one (game, team) pair. A naive join without the
    # sportsmarkettype filter would either fan out (INSERT fails on
    # gold.prediction's own PK, confirmed directly in production) or pick
    # an arbitrary non-moneyline price. Only the 'moneyline' row (0.62)
    # should ever be recorded, not the spread's 0.90.
    _reset(db_conn)
    _ensure_polymarket_market_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    game_id = _seed_decided_game(db_conn, atl, nya)
    _seed_polymarket_market_type(db_conn, "m1", "moneyline")
    _seed_polymarket_market_type(db_conn, "m2", "spreads")
    _seed_market_row(db_conn, game_id, "polymarket", atl, Decimal("0.62"), "m1:atl")
    _seed_market_row(db_conn, game_id, "polymarket", atl, Decimal("0.90"), "m2:atl")
    db_conn.commit()

    inserted = market.record(db_conn)
    db_conn.commit()

    assert inserted == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT home_win_prob FROM gold.prediction")
        rows = cur.fetchall()
    assert rows == [(Decimal("0.62"),)]

    _reset(db_conn)


def test_record_ignores_the_away_teams_own_market_row(db_conn):
    # The away team's row is the complementary side of the same market
    # (not always exactly 1 - home's price, real markets have a spread) --
    # only the home team's own row becomes home_win_prob.
    _reset(db_conn)
    _ensure_polymarket_market_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    game_id = _seed_decided_game(db_conn, atl, nya)
    _seed_polymarket_market_type(db_conn, "m1", "moneyline")
    _seed_market_row(db_conn, game_id, "polymarket", atl, Decimal("0.62"), "m1:atl")
    _seed_market_row(db_conn, game_id, "polymarket", nya, Decimal("0.35"), "m1:nya")
    db_conn.commit()

    inserted = market.record(db_conn)
    db_conn.commit()

    assert inserted == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT home_win_prob FROM gold.prediction")
        (home_win_prob,) = cur.fetchone()
    assert home_win_prob == Decimal("0.62")

    _reset(db_conn)


def test_record_keeps_polymarket_and_kalshi_as_separate_model_versions(db_conn):
    _reset(db_conn)
    _ensure_polymarket_market_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    game_id = _seed_decided_game(db_conn, atl, nya)
    _seed_polymarket_market_type(db_conn, "m1", "moneyline")
    _seed_market_row(db_conn, game_id, "polymarket", atl, Decimal("0.62"), "m1:atl")
    _seed_market_row(db_conn, game_id, "kalshi", atl, Decimal("0.58"), "KXMLBGAME-ATL")
    db_conn.commit()

    inserted = market.record(db_conn)
    db_conn.commit()

    assert inserted == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT model_version, home_win_prob FROM gold.prediction ORDER BY model_version"
        )
        rows = dict(cur.fetchall())
    assert rows["kalshi-v1"] == Decimal("0.58")
    assert rows["polymarket-v1"] == Decimal("0.62")

    _reset(db_conn)


def test_record_skips_rows_without_a_resolved_implied_probability(db_conn):
    _reset(db_conn)
    _ensure_polymarket_market_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    game_id = _seed_decided_game(db_conn, atl, nya)
    _seed_polymarket_market_type(db_conn, "m1", "moneyline")
    _seed_market_row(db_conn, game_id, "polymarket", atl, None, "m1:atl")
    db_conn.commit()

    inserted = market.record(db_conn)
    db_conn.commit()

    assert inserted == 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.prediction")
        assert cur.fetchone() == (0,)

    _reset(db_conn)


def test_record_is_idempotent(db_conn):
    # gold.prediction has no unique constraint that would reject a naive
    # duplicate insert (generated_at is part of its own composite PK,
    # defaulting to now()) -- record()'s own NOT EXISTS guard is what
    # actually prevents a second run from duplicating the same game/source.
    _reset(db_conn)
    _ensure_polymarket_market_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    game_id = _seed_decided_game(db_conn, atl, nya)
    _seed_polymarket_market_type(db_conn, "m1", "moneyline")
    _seed_market_row(db_conn, game_id, "polymarket", atl, Decimal("0.62"), "m1:atl")
    db_conn.commit()

    first = market.record(db_conn)
    db_conn.commit()
    second = market.record(db_conn)
    db_conn.commit()

    assert first == 1
    assert second == 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.prediction")
        assert cur.fetchone() == (1,)

    _reset(db_conn)


def test_health_check_flags_a_qualifying_row_that_was_never_recorded(db_conn):
    _reset(db_conn)
    _ensure_polymarket_market_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    game_id = _seed_decided_game(db_conn, atl, nya)
    _seed_polymarket_market_type(db_conn, "m1", "moneyline")
    _seed_market_row(db_conn, game_id, "polymarket", atl, Decimal("0.62"), "m1:atl")
    db_conn.commit()
    # Deliberately NOT calling market.record() -- a real qualifying row
    # exists but nothing recorded it.

    checks = market.health_check()
    check = next(
        c
        for c in checks
        if c.name
        == "decided games with a resolved polymarket moneyline price get a recorded prediction"
    )
    assert not check.ok

    _reset(db_conn)


def test_health_check_runs_cleanly_against_an_empty_database():
    checks = market.health_check()
    assert len(checks) == 4
    assert all(c.name for c in checks)


def _ensure_mlb_schedule(db_conn):
    """Do not CREATE TABLE IF NOT EXISTS with a skinny column list.

    On CI the first creator wins for the whole session. A 3-column
    mlb_schedule made later tests fail (features.build needs home_id).
    """
    columns = (
        ("game_id", "text"),
        ("game_datetime", "text"),
        ("_loaded_at", "timestamptz"),
        ("home_id", "text"),
        ("away_id", "text"),
        ("game_type", "text"),
        ("game_date", "text"),
        ("game_num", "text"),
        ("venue_id", "text"),
        ("status", "text"),
        ("_season", "text"),
    )
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        (exists,) = cur.fetchone()
        if not exists:
            colsql = ", ".join(f"{name} {typ}" for name, typ in columns)
            cur.execute(f"CREATE TABLE raw.mlb_schedule ({colsql})")
        else:
            for name, typ in columns:
                cur.execute(f"ALTER TABLE raw.mlb_schedule ADD COLUMN IF NOT EXISTS {name} {typ}")


def _ensure_live_market_tables(db_conn):
    """Full raw shapes needed to match an upcoming game to a moneyline."""
    _ensure_mlb_schedule(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS raw.polymarket_event "
            "(id text, slug text, sport text, teams text, closed text)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS raw.polymarket_market "
            "(id text, event_id text, sportsmarkettype text, volume text)"
        )
        cur.execute("ALTER TABLE raw.polymarket_market ADD COLUMN IF NOT EXISTS event_id text")
        cur.execute(
            "ALTER TABLE raw.polymarket_market ADD COLUMN IF NOT EXISTS sportsmarkettype text"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS raw.polymarket_outcome "
            "(market_id text, outcome text, price text)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS raw.polymarket_snapshot "
            "(market_id text, outcome text, price text, captured_at text)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS raw.kalshi_market "
            "(ticker text, event_ticker text, status text, volume_fp text)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS raw.kalshi_snapshot "
            "(ticker text, yes_bid_dollars text, yes_ask_dollars text, "
            "last_price_dollars text, captured_at text)"
        )
    db_conn.commit()


def _seed_upcoming_game(db_conn, atl, nya, game_pk="888001"):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(mlb_game_pk, game_instance_key, season, game_date, home_team_id, "
            "away_team_id, home_win) "
            "VALUES (%s, %s, 2026, '2026-05-23', %s, %s, NULL)",
            (game_pk, f"mlb:{game_pk}", atl, nya),
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule (game_id, game_datetime, _loaded_at) "
            "VALUES (%s, %s, '2026-05-22T12:00:00+00:00')",
            (game_pk, "2026-05-23T23:05:00+00:00"),
        )
    return game_pk


def test_record_writes_live_polymarket_moneyline_for_an_upcoming_game(db_conn):
    _reset(db_conn)
    _ensure_polymarket_market_table(db_conn)
    _ensure_live_market_tables(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    game_pk = _seed_upcoming_game(db_conn, atl, nya)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.polymarket_event (id, slug, sport, teams, closed) VALUES ("
            "'1', 'mlb-nyy-atl-2026-05-23', 'mlb', "
            "'[{''name'': ''New York Yankees'', ''ordering'': ''away''}, "
            "{''name'': ''Atlanta Braves'', ''ordering'': ''home''}]', "
            "'False')"
        )
        cur.execute(
            "INSERT INTO raw.polymarket_market (id, event_id, sportsmarkettype) "
            "VALUES ('10', '1', 'moneyline'), ('11', '1', 'spreads')"
        )
        cur.execute(
            "INSERT INTO raw.polymarket_outcome (market_id, outcome) VALUES "
            "('10', 'Atlanta Braves'), ('10', 'New York Yankees'), "
            "('11', 'Atlanta Braves')"
        )
        cur.execute(
            "INSERT INTO raw.polymarket_snapshot "
            "(market_id, outcome, price, captured_at) VALUES "
            "('10', 'Atlanta Braves', '0.55', '2026-05-23T12:00:00+00:00'), "
            "('10', 'New York Yankees', '0.45', '2026-05-23T12:00:00+00:00'), "
            "('11', 'Atlanta Braves', '0.90', '2026-05-23T12:00:00+00:00'), "
            "('10', 'Atlanta Braves', '0.99', '2026-05-24T06:00:00+00:00')"
        )
    db_conn.commit()

    inserted = market.record(db_conn)
    db_conn.commit()

    assert inserted == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT mlb_game_pk, model_version, home_win_prob FROM gold.prediction")
        rows = cur.fetchall()
    assert rows == [(game_pk, "polymarket-v1", Decimal("0.55"))]

    _reset(db_conn)


def test_record_writes_live_kalshi_moneyline_for_an_upcoming_game(db_conn):
    _reset(db_conn)
    _ensure_live_market_tables(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team_alias (team_id, alias, source) VALUES (%s, 'ATL', 'kalshi')",
            (atl,),
        )
    game_pk = _seed_upcoming_game(db_conn, atl, nya, game_pk="888002")
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.kalshi_market (ticker, event_ticker, status) VALUES "
            "('KXMLBGAME-26MAY231905NYAATL-ATL', 'KXMLBGAME-26MAY231905NYAATL', 'open')"
        )
        cur.execute(
            "INSERT INTO raw.kalshi_snapshot "
            "(ticker, yes_bid_dollars, yes_ask_dollars, last_price_dollars, captured_at) "
            "VALUES "
            "('KXMLBGAME-26MAY231905NYAATL-ATL', '0.50', '0.54', '0.52', "
            "'2026-05-23T12:00:00+00:00'), "
            "('KXMLBGAME-26MAY231905NYAATL-ATL', '0.96', '0.99', '0.97', "
            "'2026-05-24T06:00:00+00:00')"
        )
    db_conn.commit()

    inserted = market.record(db_conn)
    db_conn.commit()

    assert inserted == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT model_version, home_win_prob FROM gold.prediction")
        assert cur.fetchall() == [("kalshi-v1", Decimal("0.52"))]
    assert game_pk == "888002"

    _reset(db_conn)


def test_record_upcoming_inserts_a_new_snapshot_on_rerun(db_conn):
    # Upcoming prices move; gold.prediction is append-only snapshots, same
    # as log5/elo/gbm. Decided-game record() stays NOT EXISTS-idempotent.
    _reset(db_conn)
    _ensure_polymarket_market_table(db_conn)
    _ensure_live_market_tables(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    _seed_upcoming_game(db_conn, atl, nya, game_pk="888003")
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.polymarket_event (id, slug, sport, teams, closed) VALUES ("
            "'1', 'mlb-nyy-atl-2026-05-23', 'mlb', "
            "'[{''name'': ''New York Yankees'', ''ordering'': ''away''}, "
            "{''name'': ''Atlanta Braves'', ''ordering'': ''home''}]', "
            "'False')"
        )
        cur.execute(
            "INSERT INTO raw.polymarket_market (id, event_id, sportsmarkettype) "
            "VALUES ('10', '1', 'moneyline')"
        )
        cur.execute(
            "INSERT INTO raw.polymarket_outcome (market_id, outcome) "
            "VALUES ('10', 'Atlanta Braves')"
        )
        cur.execute(
            "INSERT INTO raw.polymarket_snapshot "
            "(market_id, outcome, price, captured_at) VALUES "
            "('10', 'Atlanta Braves', '0.55', '2026-05-23T12:00:00+00:00')"
        )
    db_conn.commit()

    first = market.record(db_conn)
    db_conn.commit()
    second = market.record(db_conn)
    db_conn.commit()

    assert first == 1
    assert second == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.prediction")
        assert cur.fetchone() == (2,)

    _reset(db_conn)
