"""Shared primitives for `mlb doctor` — see CLAUDE.md "Operational health checks".
Deliberately has no dependency on connectors or the registry, so connector
modules can import from here without creating an import cycle.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg

from mlb_baseball.db import fetch_one, get_connection

# Default freshness threshold for daily-cadence jobs (28 hours = 1680 minutes).
# Daily cron runs every 24h at 06:00 UTC; 28h leaves headroom for pipeline execution
# while catching any missed daily run well before the next day.
DAILY_FRESHNESS_THRESHOLD_MINUTES = 28 * 60


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def check_table_has_rows(table: str) -> Check:
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(f"SELECT count(*) FROM {table}")
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check(table, False, "table does not exist — never bootstrapped?")
            (count,) = fetch_one(cur)
    if count == 0:
        return Check(table, False, "0 rows — never ingested?")
    return Check(table, True, f"{count} rows")


def check_table_exists(table: str) -> Check:
    """Like check_table_has_rows, but doesn't require any rows — for genuinely
    sparse/event-driven tables where 0 rows is a valid healthy state (e.g.
    raw.mlb_live_game outside of live-game hours: nothing wrong, there's just
    nothing live to capture right now)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(f"SELECT count(*) FROM {table}")
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check(table, False, "table does not exist — never bootstrapped?")
            (count,) = fetch_one(cur)
    return Check(table, True, f"{count} rows")


def check_last_run(source: str) -> Check:
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT status, started_at FROM meta.ingestion_run "
                    "WHERE source = %s ORDER BY id DESC LIMIT 1",
                    (source,),
                )
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check(
                    f"{source} last run",
                    False,
                    "meta.ingestion_run does not exist — run `mlb migrate`",
                )
            row = cur.fetchone()
    if row is None:
        return Check(f"{source} last run", False, "never run")
    status, started_at = row
    return Check(f"{source} last run", status == "success", f"{status} at {started_at}")


def check_join_coverage(
    label: str, core_sql: str, expected_sql: str, *, tolerance: int = 0
) -> Check:
    """Compares a core table's row count against the row count its source
    join should have produced — the general safeguard for the exact bug
    class found in a research-database review (see docs/DECISIONS.md
    ADR-030 follow-up): an inner join silently drops unmatched rows (row
    loss, no trace), or a non-unique join key silently fans out (row
    duplication, no trace). Both are caught here, not just documented after
    the fact.

    Over-count (core_count > expected_count) is flagged regardless of
    `tolerance` — these joins are keyed on values that should never
    duplicate a source row, so any amount of fan-out is a bug. Under-count
    is only flagged past `tolerance`, a real, explicit allowance for a
    documented, expected gap (e.g. some rows genuinely can't resolve a
    join key) — not a blank check that hides a real regression.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(core_sql)
                (core_count,) = fetch_one(cur)
                cur.execute(expected_sql)
                (expected_count,) = fetch_one(cur)
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check(label, False, "a required table does not exist — never bootstrapped?")
    if core_count > expected_count:
        return Check(
            label, False, f"{core_count} > expected {expected_count} — possible join fan-out"
        )
    if core_count < expected_count - tolerance:
        return Check(
            label,
            False,
            f"{core_count} < expected {expected_count} (tolerance {tolerance}) — possible row loss",
        )
    return Check(label, True, f"{core_count} of {expected_count} expected")


def check_no_duplicate_key(table: str, column: str) -> Check:
    """Flags any non-NULL value in `column` that appears more than once —
    for columns used as an external join key without a DB-enforced UNIQUE
    constraint (e.g. core.game.game_pk, which can't be a real unique
    constraint since not every row resolves one — see migration
    0006_core_play_pitch.sql). This is exactly the situation that let the
    doubleheader game_pk collision bug (ADR-030 follow-up) happen
    invisibly: two core.game rows silently sharing one game_pk, corrupting
    every downstream join keyed on it."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    f"SELECT count(*) FROM (SELECT {column} FROM {table} "
                    f"WHERE {column} IS NOT NULL GROUP BY {column} HAVING count(*) > 1) x"
                )
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check(
                    f"{table}.{column} uniqueness",
                    False,
                    "table does not exist — never bootstrapped?",
                )
            (dup_count,) = fetch_one(cur)
    if dup_count > 0:
        return Check(
            f"{table}.{column} uniqueness", False, f"{dup_count} duplicate {column} values found"
        )
    return Check(f"{table}.{column} uniqueness", True, "no duplicates")


def check_partition_coverage(label: str, sql: str, *, min_ratio: float = 0.5) -> Check:
    """`sql` must return rows of (partition_key, actual_count, expected_count)
    — e.g. one row per season, comparing how many games actually landed in
    some per-game table against how many games raw.mlb_schedule says
    happened that season. Flags any single partition whose coverage ratio
    falls below `min_ratio`.

    This is deliberately per-partition, not an aggregate total: an
    aggregate check (like check_join_coverage) can pass even when one
    specific partition is silently, permanently stuck incomplete, as long
    as other partitions compensate in the sum. Found worth building after
    a real review turned up four consecutive seasons (2022-2025) with zero
    raw.mlb_win_prob coverage despite raw.mlb_schedule showing thousands of
    completed games each — season_already_loaded only checks "does at
    least one row exist," not "is this season actually complete," so an
    interrupted load can look permanently done.

    min_ratio=0.5, not 1.0: real, complete seasons calibrated directly
    against production (2015-2018) land at 100%+ coverage (a few games
    counted via doubleheaders/makeup dates push it slightly over), but a
    small number of games can have no analytics available at all (a
    confirmed, real gap — see ADR-025), so a strict 100% threshold would
    produce false positives on genuinely complete seasons. 50% cleanly
    separates "complete, minor gaps" from "barely started/never touched"
    without needing to model every edge case.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql)
                rows = cur.fetchall()
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check(label, False, "a required table does not exist — never bootstrapped?")
    incomplete = [
        (key, actual, expected)
        for key, actual, expected in rows
        if expected > 0 and actual < min_ratio * expected
    ]
    if incomplete:
        shown = ", ".join(
            f"{key}: {actual}/{expected}" for key, actual, expected in incomplete[:10]
        )
        more = f" (+{len(incomplete) - 10} more)" if len(incomplete) > 10 else ""
        return Check(label, False, f"{len(incomplete)} incomplete: {shown}{more}")
    return Check(label, True, f"{len(rows)} partitions checked, all >= {min_ratio:.0%} coverage")


def check_totals_reconcile(
    label: str, sql: str, *, tolerance: int = 0, max_mismatch_rate: float | None = None
) -> Check:
    """`sql` must return rows of (key, computed, reference) — e.g. one row
    per team-season, comparing a value derived from `core` against an
    independently-sourced reference (e.g. Lahman's own compiled win total
    for the same team-season, sourced from a completely separate raw
    table). Unlike check_join_coverage (which flags any over-count as a
    fan-out bug), this is a symmetric absolute-difference check — both
    computed > reference and computed < reference are treated the same
    way, because two independently-compiled historical sources can
    legitimately differ by a small, real, explainable amount without
    either one being wrong.

    Calibrated directly against real production data, not guessed:
    comparing core.game-derived win/loss/games totals against
    raw.lahman_teams across all of MLB history turned up ~25 team-seasons
    with a genuine mismatch, the largest being exactly 3 (1951/1962's
    famous NL pennant-tiebreaker playoffs — Retrosheet classifies those
    games game_type='playoff', matching its own convention, while
    Lahman's official standings total counts them as part of the season
    record). tolerance=3 catches a real new gap without permanently
    false-positiving on this well-understood historical pattern.

    max_mismatch_rate is for a different shape of known gap than
    tolerance: some sources have a genuine, *proportional* divergence
    baked into their own coverage (e.g. Retrosheet's own documented
    ~1.7% missing-raw-event-file rate, ADR-012/ADR-034) rather than a
    fixed small number of historical exceptions. Left unset (default),
    behavior is unchanged from before this parameter existed — any
    mismatch beyond `tolerance` fails, full stop, which is correct for
    checks like the Lahman one above where the expected mismatch count
    doesn't grow with the dataset. Set it when the expected mismatch
    *count* legitimately scales with total rows checked instead — the
    check then passes as long as the mismatch *rate* stays within it,
    not just the raw count. Without this, a per-row-tolerance-only check
    against a source with a real, fixed proportional gap can never
    return healthy once the dataset grows past a handful of rows —
    exactly what happened to starter.py's own reconciliation, found via
    `mlb doctor` reporting it failed despite matching its own documented,
    already-accepted 98.3%-clean rate.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql)
                rows = cur.fetchall()
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check(label, False, "a required table does not exist — never bootstrapped?")
    mismatched = [
        (key, computed, reference)
        for key, computed, reference in rows
        if abs(computed - reference) > tolerance
    ]
    if mismatched:
        rate = len(mismatched) / len(rows) if rows else 0.0
        if max_mismatch_rate is not None and rate <= max_mismatch_rate:
            return Check(
                label,
                True,
                f"{len(rows)} checked, {len(mismatched)} mismatched "
                f"({rate:.1%}, within accepted rate {max_mismatch_rate:.1%})",
            )
        shown = ", ".join(
            f"{key}: {computed} vs {reference}" for key, computed, reference in mismatched[:10]
        )
        more = f" (+{len(mismatched) - 10} more)" if len(mismatched) > 10 else ""
        return Check(label, False, f"{len(mismatched)} mismatched: {shown}{more}")
    return Check(label, True, f"{len(rows)} checked, all within tolerance {tolerance}")


def check_grouped_no_duplicates(label: str, sql: str) -> Check:
    """`sql` must return rows of (group_key, distinct_count, total_count)
    for groups where distinct_count < total_count is a real problem — e.g.
    one row per (season, home team, away team, date) with more than one
    core.game row, comparing how many distinct game_pk values that group
    has against how many of its rows actually have one set. Built
    specifically for doubleheader integrity: a real bug this session (see
    ADR-030's follow-up, migration 0011's own game_pk-overwrite-guard fix)
    let two different games of the same doubleheader collide onto one
    game_pk, invisible unless checked at exactly this grouping level —
    the global check_no_duplicate_key catches the same symptom, but this
    names the actual scenario (two games sharing an identity) explicitly,
    not just "some column has a repeated value somewhere."
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql)
                rows = cur.fetchall()
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check(label, False, "a required table does not exist — never bootstrapped?")
    bad = [(key, distinct, total) for key, distinct, total in rows if distinct < total]
    if bad:
        shown = ", ".join(f"{key}: {distinct}/{total}" for key, distinct, total in bad[:10])
        more = f" (+{len(bad) - 10} more)" if len(bad) > 10 else ""
        return Check(label, False, f"{len(bad)} groups with colliding identity: {shown}{more}")
    return Check(label, True, f"{len(rows)} multi-game groups checked, no collisions")


def check_recent_run(source: str, max_age_minutes: int) -> Check:
    """For sources expected to run on a repeating schedule (e.g. mlb_api's
    cron-driven live-game capture) — check_last_run only tells you whether
    the *last* run succeeded, not whether the scheduler is still running at
    all. A cron job that silently stopped (crashed host, disabled crontab
    entry, expired credentials) still has an old "success" row forever,
    which check_last_run alone would report as healthy indefinitely."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT status, started_at FROM meta.ingestion_run "
                    "WHERE source = %s ORDER BY id DESC LIMIT 1",
                    (source,),
                )
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check(
                    f"{source} freshness",
                    False,
                    "meta.ingestion_run does not exist — run `mlb migrate`",
                )
            row = cur.fetchone()
    if row is None:
        return Check(f"{source} freshness", False, "never run")
    status, started_at = row
    if status != "success":
        return Check(f"{source} freshness", False, f"last run {status}, not success")
    age = datetime.now(UTC) - started_at
    if age > timedelta(minutes=max_age_minutes):
        return Check(
            f"{source} freshness",
            False,
            f"last successful run was {age} ago (older than {max_age_minutes}m) — "
            "is the scheduled job still running? check `crontab -l`",
        )
    return Check(f"{source} freshness", True, f"last run {age} ago")
