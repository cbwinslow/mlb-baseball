"""log5 -- the simplest defensible win-probability baseline (see
docs/RESEARCH.md). No training step: two win percentages in, one
probability out. First model in the build order (ADR-032) specifically
because it proves gold.game_feature -> gold.prediction end to end before
anything more complex.
"""

from decimal import Decimal

import psycopg

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_table_has_rows
from mlb_baseball.ingest import track_run

SOURCE = "model_log5"
MODEL_VERSION = "log5-v1"


def probability(home_win_pct: Decimal, away_win_pct: Decimal) -> Decimal:
    """P(home wins) = home^2 / (home^2 + away^2) -- Bill James's log5,
    independently re-derived and validated at 97.9% efficiency across
    204,858 MLB games, 1871-2013 (see docs/RESEARCH.md). Undefined when
    both inputs are 0 (can't happen for a team with at least one prior
    game -- win_pct of exactly 0.0 is a real, distinct value from "no
    games played yet", which is NULL, not 0)."""
    home_sq = home_win_pct * home_win_pct
    away_sq = away_win_pct * away_win_pct
    return home_sq / (home_sq + away_sq)


def predict(conn: psycopg.Connection) -> int:
    # Scoped to home_win IS NULL -- games not yet decided. Without this,
    # every daily run would re-predict all 227K+ already-final historical
    # games forever, not just the handful of upcoming ones a daily cron
    # actually needs (see migration 0013's history-preserving design: this
    # scope is what makes "re-run as game day approaches" cheap instead of
    # unbounded). One-time backtesting against already-decided historical
    # games is deliberately separate, future work -- not this function.
    #
    # mlb_game_pk IS NOT NULL: gold.prediction.mlb_game_pk is NOT NULL (see
    # migration 0014) -- every still-undecided game came from raw.mlb_
    # schedule (see features.py) and so always has one, but this guards the
    # rare case of an old, incomplete historical game with a missing score
    # and no resolved game_pk (e.g. a suspended game never resumed).
    #
    # Also requires both teams to have at least one prior game this season
    # (home_win_pct/away_win_pct both non-NULL) -- log5 has no sensible
    # answer for a team's own season opener, see probability()'s docstring.
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.prediction (mlb_game_pk, model_version, home_win_prob) "
            "SELECT mlb_game_pk, %s, "
            "  (home_win_pct * home_win_pct) "
            "  / (home_win_pct * home_win_pct + away_win_pct * away_win_pct) "
            "FROM gold.game_feature "
            "WHERE home_win IS NULL AND mlb_game_pk IS NOT NULL "
            "  AND home_win_pct IS NOT NULL AND away_win_pct IS NOT NULL "
            "  AND NOT (home_win_pct = 0 AND away_win_pct = 0)",
            (MODEL_VERSION,),
        )
        return cur.rowcount


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
        backfilled = backfill_outcomes(conn)
        predicted = predict(conn)
        conn.commit()
        result["rows"] = predicted
    return {"gold.prediction (new)": predicted, "gold.prediction (outcomes backfilled)": backfilled}


def health_check() -> list[Check]:
    return [check_table_has_rows("gold.prediction")]
