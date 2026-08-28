"""Empirical Win Expectancy matrix (WIN-EXP-01, ADR-262, Plan 06).

Builds `gold.win_expectancy`: real, empirically observed P(home team wins)
for every (season, inning, half, outs, base state, score margin) combination
seen in real Retrosheet play-by-play, computed the same way as
`run_expectancy.py`'s `gold.run_expectancy_24` -- an average real outcome
given a real, observed state, not a fitted or hand-typed approximation.
Backs the Leverage Index rebuild in `run_expectancy.py`; see ADR-262 for why
the previous `avg_li` computation (a hand-typed base/out-only lookup table)
was replaced.
"""

from __future__ import annotations

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql


def compute(conn: psycopg.Connection) -> int:
    """Build gold.win_expectancy if it's empty; otherwise a no-op.

    Matches run_expectancy.py's own gold.run_expectancy_24 guard: this is a
    full-history reference table, not a per-game rolling feature, and the
    build itself is expensive (a self-join across every real historical
    play) -- safe to call unconditionally from the daily pipeline (a cheap
    COUNT check) without repeating the actual rebuild every day, which
    would risk exactly the kind of slow/fragile daily-pipeline step ADR-260
    already found and fixed once."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (event_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        (gameinfo_exists,) = fetch_one(cur)
        if not event_exists or not gameinfo_exists:
            return 0
        cur.execute("SELECT count(*) FROM gold.win_expectancy")
        (we_count,) = fetch_one(cur)
        if we_count > 0:
            return 0
        cur.execute(read_sql("win_expectancy_matrix_build.sql"))
        return cur.rowcount


def health_check() -> list[Check]:
    """Verify the win-expectancy table exists, has real coverage, and its
    values fall in known-sensible ranges at the extremes (near-certain wins
    and losses should be close to 1.0/0.0; a tied game at the very first
    plate appearance should sit close to real MLB home-field advantage)."""
    checks: list[Check] = []
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*), sum(sample_size) FROM gold.win_expectancy")
            row_count, total_samples = fetch_one(cur)
            if row_count == 0:
                checks.append(
                    Check("win_expectancy coverage", False, "gold.win_expectancy is empty")
                )
                return checks
            checks.append(
                Check(
                    "win_expectancy coverage",
                    True,
                    f"{row_count} states, {total_samples} real observations",
                )
            )

            cur.execute(
                "SELECT avg(home_win_pct) FROM gold.win_expectancy "
                "WHERE inning_bucket = 1 AND is_bottom = false AND outs_before = 0 "
                "AND base_state = '000' AND margin_bucket = 0"
            )
            row = cur.fetchone()
            first_pa_we = row[0] if row else None
            if first_pa_we is not None and 0.50 <= float(first_pa_we) <= 0.58:
                checks.append(
                    Check(
                        "win_expectancy home-field-advantage sanity",
                        True,
                        f"tied game, top 1st, bases empty: {float(first_pa_we):.4f} "
                        "(real MLB home-field advantage is ~0.53-0.54)",
                    )
                )
            else:
                checks.append(
                    Check(
                        "win_expectancy home-field-advantage sanity",
                        False,
                        f"unexpected value at first PA: {first_pa_we}",
                    )
                )

            cur.execute(
                "SELECT avg(home_win_pct) FROM gold.win_expectancy "
                "WHERE inning_bucket = 9 AND is_bottom = true AND outs_before = 2 "
                "AND base_state = '000' AND margin_bucket <= -3"
            )
            row = cur.fetchone()
            near_loss_we = row[0] if row else None
            if near_loss_we is not None and float(near_loss_we) <= 0.05:
                checks.append(
                    Check(
                        "win_expectancy near-certain-loss sanity",
                        True,
                        f"bottom 9th, 2 outs, down 3+: {float(near_loss_we):.4f} (near 0)",
                    )
                )
            else:
                checks.append(
                    Check(
                        "win_expectancy near-certain-loss sanity",
                        False,
                        f"unexpected value in a near-certain-loss state: {near_loss_we}",
                    )
                )
    except Exception as exc:
        checks.append(Check("win_expectancy", False, str(exc)))
    return checks
