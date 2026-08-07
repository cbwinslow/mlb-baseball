"""Market-implied win probability as a comparison line against log5/Elo/
gbm's own predictions (ADR-053, closing the ROADMAP's "next" item after
ADR-052 made core.market.implied_probability leakage-safe).

Deliberately named record(), not predict() -- unlike log5.py/elo.py/
gbm.py, which only ever run against still-upcoming games (gold.game_
feature.home_win IS NULL), a market's implied_probability can only ever
resolve for an ALREADY-DECIDED game: core.market.game_id is matched via
core.game (see conform.py's _game_lookup), and core.game only ever holds
completed games by design (features.py's own docstring). So this is
retrospective by construction, not a live prediction feed -- "how well
has the market's own pre-game price predicted real outcomes, compared to
our models" -- not "here's the market's price for tomorrow's game." A
genuinely live version (matching market data to still-upcoming games)
would need core.market's own matching extended the same way starter.py's
compute_probable()/bullpen.py's compute_upcoming() extended their own
features to raw.mlb_schedule instead of core.game -- a real, separate
follow-up (see issue tracker), not built here.

Polymarket and Kalshi are recorded as two distinct model_versions
('polymarket-v1'/'kalshi-v1'), never blended into one -- same
"keep distinct signals distinct" precedent core.market.source itself
already establishes; blending would also throw away the ability to
compare the two markets against each other, a real, free byproduct of
keeping them separate.

Only the home team's own core.market row becomes home_win_prob -- the
away team's row is the complementary side of the same market (not always
exactly 1 - home_win_prob, since real markets have a spread/vig), and
gold.prediction's own schema only ever stores one probability per game
(the same shape log5/elo/gbm already use).

Idempotent via an explicit NOT EXISTS guard, not gold.prediction's own
schema (game_pk, model_version, generated_at) is a composite PK with
generated_at defaulting to now(), so a naive re-run would insert a new,
duplicate-in-spirit row every time -- unlike log5/elo/gbm, which get
idempotency for free from only ever targeting home_win IS NULL rows (a
game exits that scope forever once decided), record() has no such
natural boundary since it only ever targets already-decided games.

Real bug found running this against production, not hypothetical: a
single Polymarket event carries multiple distinct markets sharing the
exact same game+team match -- moneyline, run-line spreads, first-five-
innings spreads (confirmed directly: PHI@BAL 2026-08-02 alone had 7
distinct market_ids all resolving to the same (game, team) pair, values
ranging from 0.19 to 0.81, nothing like "one team's win probability").
core.market itself carries no market-type column to distinguish them
(ADR-026's original scope flattened every matched market type into one
table), so this joins back to raw.polymarket_market's own
`sportsmarkettype = 'moneyline'` to resolve exactly one row per (game,
team) -- confirmed directly against all of production, not just this one
example: filtering to moneyline leaves exactly one qualifying row per
(game, team), zero exceptions either direction. Kalshi doesn't have this
problem at all: _kalshi_market_rows (conform.py) already scopes to
`event_ticker LIKE 'KXMLBGAME%'`, Kalshi's own daily-moneyline-only
series (ADR-049), confirmed directly (zero (game, team) pairs with more
than one non-NULL Kalshi row) -- so only the Polymarket query needs the
extra join/filter, not a shared parameterized shape forced onto both.
"""

import psycopg

from mlb_baseball.health import Check, check_join_coverage
from mlb_baseball.sql import read_sql

MODEL_VERSIONS = {"polymarket": "polymarket-v1", "kalshi": "kalshi-v1"}


def record(conn: psycopg.Connection) -> int:
    total = 0
    with conn.cursor() as cur:
        cur.execute(
            read_sql("market_polymarket_prediction_insert.sql"),
            {"model_version": MODEL_VERSIONS["polymarket"]},
        )
        total += cur.rowcount
        cur.execute(
            read_sql("market_kalshi_prediction_insert.sql"),
            {"model_version": MODEL_VERSIONS["kalshi"]},
        )
        total += cur.rowcount
    return total


def _polymarket_coverage_check() -> Check:
    model_version = MODEL_VERSIONS["polymarket"]
    # tolerance=0: a qualifying, moneyline-filtered core.market row has
    # everything record()'s INSERT needs, so any gap means record() either
    # hasn't run or something broke.
    return check_join_coverage(
        "decided games with a resolved polymarket moneyline price get a recorded prediction",
        f"""
        SELECT count(*) FROM gold.prediction p
        JOIN gold.game_feature f ON f.game_instance_key = p.game_instance_key
        JOIN core.game g ON g.id = f.game_id
        WHERE p.model_version = '{model_version}'
        """,
        """
        SELECT count(*)
        FROM core.market m
        JOIN core.game g ON g.id = m.game_id AND g.home_team_id = m.team_id
        JOIN raw.polymarket_market pm ON pm.id = split_part(m.market_ref, ':', 1)
        WHERE m.source = 'polymarket'
            AND pm.sportsmarkettype = 'moneyline'
            AND m.implied_probability IS NOT NULL
            AND g.game_pk IS NOT NULL
        """,
        tolerance=0,
    )


def _kalshi_coverage_check() -> Check:
    model_version = MODEL_VERSIONS["kalshi"]
    return check_join_coverage(
        "decided games with a resolved kalshi price get a recorded prediction",
        f"""
        SELECT count(*) FROM gold.prediction p
        JOIN gold.game_feature f ON f.game_instance_key = p.game_instance_key
        JOIN core.game g ON g.id = f.game_id
        WHERE p.model_version = '{model_version}'
        """,
        """
        SELECT count(*)
        FROM core.market m
        JOIN core.game g ON g.id = m.game_id AND g.home_team_id = m.team_id
        WHERE m.source = 'kalshi'
            AND m.implied_probability IS NOT NULL
            AND g.game_pk IS NOT NULL
        """,
        tolerance=0,
    )


def health_check() -> list[Check]:
    return [_polymarket_coverage_check(), _kalshi_coverage_check()]
