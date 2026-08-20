"""Home-minus-away interaction terms (ADR-081, admission queue INT-01,
docs/FEATURE_ADMISSION_QUEUE.md). Pure algebra over already-approved,
already-populated gold.game_feature column pairs -- no new raw
dependency, no join, same "derive from a prior step's own output" shape
as team_rate.py::compute_run_environment.

Tree-based models (gbm-v1) can in principle learn a difference from two
raw inputs on their own, but a linear model (log5/elo) cannot, and an
explicit difference still makes the signal a single split can act on
directly rather than requiring the tree to reconstruct it -- a cheap,
zero-new-data feature worth trying, not assumed to help until evaluated
in a real retrain (a separate, later step, matching every other feature
family's own "build first, evaluate separately" precedent, e.g. ADR-061).

Scope: exactly the six most foundational already-approved paired team
features (win_pct, win_pct_10, pyth_wpct, elo, woba, wrc_plus) -- not
every possible home/away pair on gold.game_feature. INT-01's own
admission-queue row calls for "approved" pairs; this is a deliberately
narrow, defensible starting set, not an attempt to exhaustively difference
every column that happens to exist in home_X/away_X form.

Computed unconditionally (no to_regclass gate, no raw-table dependency)
-- every column it reads already exists on gold.game_feature's base
schema, so this always has something to compute, even on a completely
fresh database before any Retrosheet-derived enrichment has run (the
result is simply NULL - NULL = NULL for every row until those columns are
populated, which is correct, not an error).
"""

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(read_sql("int_diff_update.sql"))
        return cur.rowcount


def health_check() -> list[Check]:
    """Proves each diff column actually equals home minus away wherever
    both sides are populated -- not a plausible-range check (a difference
    of two rates/ratings has no natural bound of its own), but a direct
    algebraic-parity check, matching INT-01's own admission-queue test
    requirement ("algebra parity and no fanout")."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT "
            "count(*) FILTER (WHERE win_pct_diff IS DISTINCT FROM (home_win_pct - away_win_pct)), "
            "count(*) FILTER ("
            "  WHERE win_pct_10_diff IS DISTINCT FROM (home_win_pct_10 - away_win_pct_10)"
            "), "
            "count(*) FILTER ("
            "  WHERE pyth_wpct_diff IS DISTINCT FROM (home_pyth_wpct - away_pyth_wpct)"
            "), "
            "count(*) FILTER (WHERE elo_diff IS DISTINCT FROM (home_elo - away_elo)), "
            "count(*) FILTER (WHERE woba_diff IS DISTINCT FROM (home_woba - away_woba)), "
            "count(*) FILTER ("
            "  WHERE wrc_plus_diff IS DISTINCT FROM (home_wrc_plus - away_wrc_plus)"
            ") "
            "FROM gold.game_feature"
        )
        (
            bad_win_pct,
            bad_win_pct_10,
            bad_pyth_wpct,
            bad_elo,
            bad_woba,
            bad_wrc_plus,
        ) = fetch_one(cur)

    def _check(name: str, bad: int) -> Check:
        if bad:
            return Check(name, False, f"{bad} rows where {name} != home - away")
        return Check(name, True, "every row matches home - away")

    return [
        _check("win_pct_diff", bad_win_pct),
        _check("win_pct_10_diff", bad_win_pct_10),
        _check("pyth_wpct_diff", bad_pyth_wpct),
        _check("elo_diff", bad_elo),
        _check("woba_diff", bad_woba),
        _check("wrc_plus_diff", bad_wrc_plus),
    ]
