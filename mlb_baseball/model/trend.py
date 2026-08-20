"""Recent-minus-long win-rate trend (ADR-081, admission queue INT-02,
docs/FEATURE_ADMISSION_QUEUE.md). Pure algebra over two already-approved,
already-populated gold.game_feature columns per side (win_pct_10 minus
win_pct) -- no new raw dependency, no join.

win_pct_10 (trailing 10-game rolling rate) and win_pct (season-to-date
expanding rate) are both already computed by game_feature_rebuild.sql's
own w_last10/w_season windows (migration 0012) -- this is the one
already-approved family this project has with both a "recent" and a
"long" version already built. INT-02's own admission-queue row calls for
"rolling rate minus expanding rate" over "approved prior rates" in
general; this module covers exactly the one pair that exists today, not
a speculative rolling-window build for every other rate family (OBP/SLG/
FIP/etc. only have an expanding version so far -- building a fresh
trailing-window variant for any of those is separate, larger work, not
bundled into this narrowly-scoped change).

Positive means a team is playing better lately than its season rate;
negative means worse -- a real, interpretable signal distinct from either
input alone, and (like diff.py's home-minus-away terms) a signal a
tree-based model could in principle reconstruct from win_pct/win_pct_10
directly, but an explicit column makes available to a single split
without requiring the tree to do that reconstruction itself. Whether it
actually helps gbm-v1's held-out log-loss is a separate, later retrain
question, not assumed here.
"""

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(read_sql("trend_update.sql"))
        return cur.rowcount


def health_check() -> list[Check]:
    """Algebraic parity check, matching INT-02's own admission-queue test
    requirement ("window boundary/no future data" -- proving the stored
    value really is win_pct_10 - win_pct, not a plausible-range bound,
    since a rate-minus-rate difference has no natural bound of its own)."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT "
            "count(*) FILTER ("
            "  WHERE home_win_pct_trend IS DISTINCT FROM (home_win_pct_10 - home_win_pct)"
            "), "
            "count(*) FILTER ("
            "  WHERE away_win_pct_trend IS DISTINCT FROM (away_win_pct_10 - away_win_pct)"
            ") "
            "FROM gold.game_feature"
        )
        bad_home, bad_away = fetch_one(cur)

    def _check(name: str, bad: int, formula: str) -> Check:
        if bad:
            return Check(name, False, f"{bad} rows where {name} != {formula}")
        return Check(name, True, f"every row matches {formula}")

    return [
        _check("home_win_pct_trend", bad_home, "home_win_pct_10 - home_win_pct"),
        _check("away_win_pct_trend", bad_away, "away_win_pct_10 - away_win_pct"),
    ]
