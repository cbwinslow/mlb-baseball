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
            cur.execute(
                "CREATE TABLE raw.polymarket_market (id text, sportsmarkettype text)"
            )
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
        cur.execute("SELECT to_regclass('raw.polymarket_market')")
        (exists,) = cur.fetchone()
        if exists:
            cur.execute("DELETE FROM raw.polymarket_market")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.market")
        cur.execute("DELETE FROM core.game")
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
            "SELECT mlb_game_pk, model_version, home_win_prob, actual_home_win "
            "FROM gold.prediction"
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
    assert len(checks) == 2
    assert all(c.name for c in checks)
