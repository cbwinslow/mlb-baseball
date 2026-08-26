"""Empirical Leverage Index matrix (LEV-EMPIRICAL-01, ADR-262, Plan 06).

Builds `gold.leverage_index`: the real, empirically observed win-expectancy
swing for every (inning, half, outs, base state, score margin) state,
normalized so the league-wide average state is exactly 1.0 -- the standard
Leverage Index convention. See `mlb_baseball/sql/leverage_index_matrix_build.sql`
for the full derivation and `gold.win_expectancy`
(`mlb_baseball/model/win_expectancy.py`) for the win-expectancy table this
is built from. Replaces the hand-typed, unvalidated leverage table
previously used directly inside `run_expectancy.py`; see ADR-262.
"""

from __future__ import annotations

import logging
import time

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql

logger = logging.getLogger(__name__)


def compute(conn: psycopg.Connection) -> int:
    """Build gold.leverage_index if it's empty; otherwise a no-op. Same
    "expensive full-history reference table, build once" reasoning as
    win_expectancy.compute() -- see its docstring.

    Built one real season at a time (~123 seasons, 1900-2025), not as a
    single query over the full ~16M-row raw.retrosheet_event table --
    confirmed directly: the single-query version ran 4.5+ hours against
    real production with no way to tell whether it was making progress
    (Postgres has no progress view for a plain SELECT/INSERT). Chunking by
    season makes real per-chunk timing and row counts directly observable
    from the logs between calls, and each chunk only needs to plan/execute
    over ~1/123rd of the real data. See leverage_index_season_partial.sql
    / leverage_index_matrix_finalize.sql for the exact math (SUM/COUNT
    pooled across seasons afterward -- identical to a single-pass AVG, not
    an approximation of it)."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (event_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        (gameinfo_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('gold.win_expectancy')")
        (we_exists,) = fetch_one(cur)
        if not event_exists or not gameinfo_exists or not we_exists:
            return 0
        cur.execute("SELECT count(*) FROM gold.win_expectancy")
        (we_count,) = fetch_one(cur)
        if we_count == 0:
            return 0
        cur.execute("SELECT count(*) FROM gold.leverage_index")
        (li_count,) = fetch_one(cur)
        if li_count > 0:
            return 0
        cur.execute("SELECT DISTINCT _season::integer FROM raw.retrosheet_event ORDER BY 1")
        seasons = [row[0] for row in cur.fetchall()]

    partial_sql = read_sql("leverage_index_season_partial.sql")
    for i, season in enumerate(seasons, start=1):
        t0 = time.time()
        with conn.cursor() as cur:
            # See leverage_index.py's module docstring / migration 0086 for
            # why both settings are needed: the real cardinality
            # misestimate on lower(gametype)/outs_ct::integer (fixed by
            # migration 0086's indexes) and the sort/hash work's own
            # disk-spill tendency at default work_mem, both real, both
            # confirmed directly against production. Still applied
            # per-chunk since each is session-local (SET LOCAL) and this
            # loop opens a fresh cursor each iteration; per-season data
            # volume is far smaller now, so 512MB is ample headroom rather
            # than the earlier single-query build's 2GB.
            cur.execute("SET LOCAL enable_nestloop = off")
            cur.execute("SET LOCAL work_mem = '512MB'")
            cur.execute(partial_sql, {"season": season})
        conn.commit()
        logger.info(
            "leverage_index: season %s done (%d/%d) in %.1fs",
            season,
            i,
            len(seasons),
            time.time() - t0,
        )

    with conn.cursor() as cur:
        cur.execute(read_sql("leverage_index_matrix_finalize.sql"))
        rowcount = cur.rowcount
        cur.execute("DELETE FROM gold.leverage_index_staging")
    conn.commit()
    return rowcount


def health_check() -> list[Check]:
    """Verify the leverage-index table exists, has real coverage, and its
    values fall in known-sensible ranges: the league-wide average across
    every state should be close to the defining 1.0, and a real, widely
    recognized maximum-leverage situation (bottom of the 9th, bases loaded,
    0 outs, tied) should be well above 1.0."""
    checks: list[Check] = []
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*), sum(sample_size) FROM gold.leverage_index")
            row_count, total_samples = fetch_one(cur)
            if row_count == 0:
                checks.append(
                    Check("leverage_index coverage", False, "gold.leverage_index is empty")
                )
                return checks
            checks.append(
                Check(
                    "leverage_index coverage",
                    True,
                    f"{row_count} states, {total_samples} real observations",
                )
            )

            cur.execute(
                "SELECT sum(leverage_index * sample_size) / sum(sample_size) "
                "FROM gold.leverage_index"
            )
            row = cur.fetchone()
            weighted_avg = row[0] if row else None
            if weighted_avg is not None and 0.85 <= float(weighted_avg) <= 1.15:
                checks.append(
                    Check(
                        "leverage_index normalization sanity",
                        True,
                        f"sample-weighted average LI: {float(weighted_avg):.4f} (should be ~1.0)",
                    )
                )
            else:
                checks.append(
                    Check(
                        "leverage_index normalization sanity",
                        False,
                        f"sample-weighted average LI far from 1.0: {weighted_avg}",
                    )
                )

            cur.execute(
                "SELECT leverage_index FROM gold.leverage_index "
                "WHERE inning_bucket = 9 AND is_bottom = true AND outs_before = 0 "
                "AND base_state = '111' AND margin_bucket = 0"
            )
            row = cur.fetchone()
            walkoff_li = row[0] if row else None
            if walkoff_li is not None and float(walkoff_li) >= 2.0:
                checks.append(
                    Check(
                        "leverage_index high-leverage sanity",
                        True,
                        f"bottom 9th, bases loaded, 0 outs, tied: LI={float(walkoff_li):.2f} "
                        "(well above 1.0, as a real high-leverage situation should be)",
                    )
                )
            else:
                checks.append(
                    Check(
                        "leverage_index high-leverage sanity",
                        False,
                        f"unexpectedly low LI in a known high-leverage state: {walkoff_li}",
                    )
                )
    except Exception as exc:
        checks.append(Check("leverage_index", False, str(exc)))
    return checks
