"""Phase 2 modeling (ADR-032/033/034, docs/RESEARCH.md). Deliberately not
a plugin framework -- features/elo/starter build up gold.game_feature's
columns, log5/elo/gbm are the models that consume them; this just calls
each directly, in order, inside one transaction. Extract real structure
once a piece actually needs something the others don't fit into this same
shape, not before -- same reasoning as this project's connector registry,
which came after multiple real connectors, not in anticipation of one.

backfill_outcomes lives here, not inside any one model, because it isn't
model-specific -- it fills in the actual result for *every* model's
predictions once a game is decided, regardless of which model made them.

gbm.train() is deliberately NOT called from run() -- training is a
distinct, occasional operation (see gbm.py's own docstring and ADR-033),
triggered separately via `mlb train`. run() (mlb predict) only ever loads
whatever model train() last saved -- which means gbm-v1 won't use the new
starter-quality columns until it's retrained against them (a real,
separate follow-up, not automatic just because the columns now exist).
"""

import psycopg

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check
from mlb_baseball.ingest import track_run
from mlb_baseball.model import (
    bullpen,
    elo,
    evaluation,
    features,
    framing,
    gbm,
    log5,
    market,
    oaa,
    offense,
    park,
    speed,
    starter,
    war,
)

SOURCE = "model"


def backfill_outcomes(conn: psycopg.Connection) -> int:
    """Fills in actual_home_win for any gold.prediction row whose game is
    now final -- without this, prediction history never accumulates a
    calibration record (the whole reason gold.prediction exists, see
    ADR-032). Joined via game_pk, not game_id -- a prediction made while a
    game was still upcoming has no core.game row to key on until conform
    picks it up after the game finishes."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.prediction p "
            "SET actual_home_win = (g.home_score > g.away_score) "
            "FROM core.game g "
            "WHERE g.game_pk = p.mlb_game_pk AND p.actual_home_win IS NULL "
            "  AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL"
        )
        return cur.rowcount


def run() -> dict[str, int]:
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        feature_count = features.build(conn)
        elo.compute_ratings(conn)
        starter_count = starter.compute(conn)
        starter.compute_live(conn)
        starter.compute_probable(conn)
        park.compute(conn)
        offense.compute(conn)
        offense.compute_wrc_plus(conn)
        offense.compute_live(conn)
        offense.compute_wrc_plus_live(conn)
        war.compute(conn)
        bullpen.compute(conn)
        bullpen.compute_live(conn)
        bullpen.compute_upcoming(conn)
        oaa.compute(conn)
        speed.compute(conn)
        framing.compute(conn)
        # market.record() runs before backfill_outcomes(), not after --
        # unlike log5/elo/gbm's own predictions (made for still-upcoming
        # games, where actual_home_win is legitimately unknown yet), every
        # market prediction is for a game that's already decided by
        # construction (see market.py's own docstring). Recording it after
        # backfill_outcomes() would leave a real, already-known outcome
        # sitting NULL for a full extra cron cycle for no reason -- found
        # running this against production, not hypothetical.
        market_count = market.record(conn)
        backfilled = backfill_outcomes(conn)
        log5_count = log5.predict(conn)
        elo_count = elo.predict(conn)
        gbm_count = gbm.predict(conn)
        conn.commit()
        result["rows"] = feature_count + log5_count + elo_count + gbm_count + market_count
    return {
        "gold.game_feature": feature_count,
        "gold.game_feature (starters updated)": starter_count,
        "gold.prediction (log5)": log5_count,
        "gold.prediction (elo)": elo_count,
        "gold.prediction (gbm)": gbm_count,
        "gold.prediction (market)": market_count,
        "gold.prediction (outcomes backfilled)": backfilled,
    }


def train() -> dict:
    with get_connection() as conn:
        return gbm.train(conn)


def evaluate(
    model_versions: list[str], season: int, cutoff: str, bootstrap_samples: int
) -> dict:
    with get_connection() as conn:
        return evaluation.evaluate(conn, model_versions, season, cutoff, bootstrap_samples)


def health_check() -> list[Check]:
    return (
        features.health_check()
        + log5.health_check()
        + gbm.health_check()
        + starter.health_check()
        + park.health_check()
        + offense.health_check()
        + war.health_check()
        + bullpen.health_check()
        + oaa.health_check()
        + speed.health_check()
        + framing.health_check()
        + market.health_check()
    )
