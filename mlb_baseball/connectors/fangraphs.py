"""Lands FanGraphs' public bulk data into ``raw.fangraphs_*`` via the ``fungo``
library (``fungo.fangraphs``), which reaches FanGraphs through its mobile-app
JSON API using the one Cloudflare-exempt User-Agent (``okhttp/4.12.0``).

Why not pybaseball: ``pybaseball``'s FanGraphs path
(``batting_stats()``/``pitching_stats()`` -> ``leaders-legacy.aspx``) is
permanently HTTP 403 — fangraphs.com sits behind Cloudflare, which
TLS-fingerprint-blocks generic clients. Confirmed and recorded in
``docs/DATA_SOURCES.md`` and ADR-288. ``fungo`` rides the FanGraphs mobile
app's ``okhttp/4.12.0`` client, the one documented exemption. That exemption
is load-bearing and could be withdrawn: ``fungo`` raises ``FangraphsError``
naming the condition on a 403, and this connector re-raises it (never an
infinite retry) so ``mlb doctor`` goes red and the fix is a ``fungo`` upgrade,
not a local patch.

Tables and replace strategy (see the sidecar for the full contract):

- ``raw.fangraphs_batting`` / ``_pitching`` / ``_fielding`` — season
  leaderboards, one row per player-season (``ind=1``), everyone (``qual=0``),
  full available history, per-season scoped replace on ``_season``.
- ``raw.fangraphs_guts`` — the Guts! wOBA/FIP constant table, full history in
  one call, whole-table replace.
- ``raw.fangraphs_park_factors`` / ``_park_factors_handedness`` — per season,
  scoped replace on ``_season``.
- ``raw.fangraphs_prospects`` — THE BOARD, per season, scoped replace.
- ``raw.fangraphs_split_batting`` / ``_split_pitching`` — a curated set of
  league-wide splits (vs LHP/RHP, home, road, by month), per season per
  split, scoped replace on a compound ``_scope`` = ``"{season}|{split}"``
  (``_season`` / ``_split`` kept as convenience columns). NOT the full
  292-code catalogue and no per-player-only FanGraphs endpoint — same
  combinatorial rationale as ADR-020 / ADR-024.
- ``raw.fangraphs_projection`` — every preseason and rest-of-season
  projection system ``fungo`` exposes, stored append-only as a dated
  snapshot. A ``_row_hash`` of the projected values drives change detection:
  a run appends a new snapshot for a ``(_projection_system, _stat_group,
  playerid)`` key only when its values differ from that key's most recent
  stored snapshot, so an unchanged projection does not accumulate duplicate
  rows. This is how the history of a moving projection is retained (ADR-048
  probable-pitcher pattern).

Deferred, not built here (documented follow-ups, not gaps):
``get_player_stats`` / ``get_game_log`` (per player per season — combinatorial),
the full 292-code split catalogue, minor-league leaderboards, and
RosterResource depth charts (``get_depth_chart`` needs a hand-verified 30-team
URL-slug table and returns a nested React-cache payload, not a leaderboard;
MLB Stats API already covers rosters/probables).

Runtime: ``fungo`` does its own bounded exponential-backoff retry on transient
(5xx/network/timeout) failures and raises immediately on 4xx, so
``net.call_with_retry`` (which only catches ``requests`` exceptions) is not
used. ``bootstrap()`` loops history at the season grain with a
``season_already_loaded`` skip and per-unit try/except; ``update()`` reloads
the current season for every board plus a projection snapshot. FanGraphs data
is ``local_research`` only (``docs/SOURCE_RIGHTS.md``); the ingest guard
blocks this connector under any other profile. Not on its own cron beyond
``mlb update``; ``scripts/fangraphs_update.sh`` runs ``update()`` every 6h to
capture projection movement. ``health_check()`` uses the shared daily
freshness threshold scoped to ``mode="update"``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime

import fungo.fangraphs as fg
import pandas as pd
import psycopg
from fungo.exceptions import FangraphsError, RequestError

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import (
    DAILY_FRESHNESS_THRESHOLD_MINUTES,
    Check,
    check_last_run,
    check_recent_run,
    check_table_has_rows,
)
from mlb_baseball.ingest import track_run
from mlb_baseball.load import append_dataframe, load_dataframe, season_already_loaded

SOURCE = "fangraphs"
FRESHNESS_THRESHOLD_MINUTES = DAILY_FRESHNESS_THRESHOLD_MINUTES

# Earliest season attempted per product. FanGraphs' standard leaderboards
# reach back to the 19th century; advanced columns simply come back null for
# early years (preserved as genuine nulls, never zero-filled). The real
# observed first season per board is recorded in the sidecar after a bootstrap.
# Tests override these (see bref.FIRST_YEAR for the same pattern).
LEADERBOARD_FIRST_YEAR = 1871
PARK_FACTOR_FIRST_YEAR = 1871
PROSPECT_FIRST_YEAR = 2010
SPLIT_FIRST_YEAR = 2002  # FanGraphs' split-stats era

LEADERBOARDS: list[tuple[str, str]] = [
    ("raw.fangraphs_batting", "bat"),
    ("raw.fangraphs_pitching", "pit"),
    ("raw.fangraphs_fielding", "fld"),
]

# Curated league-wide splits (spec: at minimum vs LHP/RHP, home, road, by
# month). Names resolve via fungo.fangraphs.SPLIT_CODES.
CURATED_SPLITS: list[str] = [
    "vs_lhp",
    "vs_rhp",
    "home",
    "away",
    "march_april",
    "may",
    "june",
    "july",
    "august",
    "sept_oct",
]
SPLIT_BOARDS: list[tuple[str, str]] = [
    ("raw.fangraphs_split_batting", "B"),
    ("raw.fangraphs_split_pitching", "P"),
]

PRESEASON_SYSTEMS: list[str] = list(fg.PROJECTION_SYSTEMS)
ROS_SYSTEMS: list[str] = list(fg.ROS_PROJECTION_SYSTEMS)
PROJECTION_STAT_GROUPS: list[str] = ["bat", "pit"]
PROJECTION_TABLE = "raw.fangraphs_projection"
_PROJECTION_KEY = ("_projection_system", "_stat_group", "playerid")
_PROJECTION_IDENTITY = ("_projection_system", "_stat_group", "playerid", "_captured_date")

# FanGraphs' leaderboards carry sign-variant column names that collide once
# Postgres-sanitized (``-WPA`` and ``+WPA`` both -> ``_wpa``; ``K-BB%`` and
# ``K/BB+`` both -> ``k_bb_``). `load_dataframe` fails closed on a collision
# rather than silently merging two columns, so rename them to distinct,
# meaning-preserving names before load. The collision check stays as the
# backstop: a NEW colliding column from a future FanGraphs change fails loudly
# here instead of quietly losing data (verified against every board 2026-09-10).
_COLUMN_RENAMES = {
    "-WPA": "WPA_neg",
    "+WPA": "WPA_pos",
    "K-BB%": "K_minus_BB_pct",
    "K/BB+": "K_per_BB_plus",
}


def _frame(rows: list[dict]) -> pd.DataFrame:
    """A DataFrame from a fungo response, with FanGraphs' colliding sign-variant
    columns renamed (see ``_COLUMN_RENAMES``)."""
    df = pd.DataFrame(rows)
    overlap = {src: dst for src, dst in _COLUMN_RENAMES.items() if src in df.columns}
    return df.rename(columns=overlap) if overlap else df


def _fg_call(fn: Callable, *args, **kwargs):
    """Call a ``fungo.fangraphs`` function. ``fungo`` already does bounded
    exponential-backoff retry on transient (5xx/network/timeout) failures and
    raises immediately on 4xx. A ``FangraphsError`` (the ``okhttp/4.12.0``
    Cloudflare exemption withdrawn -> HTTP 403) or a ``RequestError`` (retries
    exhausted) is logged verbatim and re-raised — never retried again, never
    an infinite loop. See ADR-288."""
    try:
        return fn(*args, **kwargs)
    except (FangraphsError, RequestError) as exc:
        name = getattr(fn, "__name__", repr(fn))
        print(f"fangraphs: {name}{args!r} failed ({type(exc).__name__}: {exc})")
        raise


def _run_unit(conn: psycopg.Connection, label: str, fn: Callable, *args) -> int:
    """Run one load unit, commit on success, roll back and skip on failure —
    the per-season/per-table isolation every connector uses so one unit's
    network hiccup does not lose the run's committed progress."""
    try:
        count = fn(conn, *args)
        conn.commit()
        return count
    except Exception as exc:  # noqa: BLE001 — deliberately broad, logged + skipped
        conn.rollback()
        print(f"fangraphs: {label} failed ({exc}); skipping")
        return 0


# --------------------------------------------------------------------------
# Season leaderboards
# --------------------------------------------------------------------------


def _load_leaderboard(conn: psycopg.Connection, table: str, stat_group: str, season: int) -> int:
    rows = _fg_call(fg.get_leaders, stat_group, season, season, ind=1, qual=0)
    df = _frame(rows)
    if df.empty:
        return 0
    df["_season"] = str(season)
    return load_dataframe(conn, table, df, scope_column="_season", scope_value=str(season))


# --------------------------------------------------------------------------
# Reference boards: guts, park factors, prospects
# --------------------------------------------------------------------------


def _load_guts(conn: psycopg.Connection) -> int:
    rows = _fg_call(fg.get_guts_constants)
    df = _frame(rows)
    if df.empty:
        return 0
    return load_dataframe(conn, "raw.fangraphs_guts", df)


_PARK_FACTOR_BOARDS: list[tuple[str, Callable]] = [
    ("raw.fangraphs_park_factors", fg.get_park_factors),
    ("raw.fangraphs_park_factors_handedness", fg.get_park_factors_by_handedness),
]


def _load_park_factors(conn: psycopg.Connection, season: int) -> int:
    total = 0
    for table, fn in _PARK_FACTOR_BOARDS:
        rows = _fg_call(fn, season)
        df = _frame(rows)
        if df.empty:
            continue
        df["_season"] = str(season)
        total += load_dataframe(conn, table, df, scope_column="_season", scope_value=str(season))
    return total


def _load_prospects(conn: psycopg.Connection, season: int) -> int:
    rows = _fg_call(fg.get_prospect_board, season)
    df = _frame(rows)
    if df.empty:
        return 0
    df["_season"] = str(season)
    # THE BOARD's columns change materially season to season (new grade
    # columns added, others renamed/dropped) — that is the source evolving,
    # not a bug to warn about on every historical season.
    return load_dataframe(
        conn,
        "raw.fangraphs_prospects",
        df,
        scope_column="_season",
        scope_value=str(season),
        schema_drift_policy="ignore",
    )


# --------------------------------------------------------------------------
# Curated split leaderboards
# --------------------------------------------------------------------------


def _load_split_board(
    conn: psycopg.Connection, table: str, position: str, season: int, split: str
) -> int:
    rows = _fg_call(fg.get_split_leaders, position, season, split)
    df = _frame(rows)
    if df.empty:
        return 0
    scope = f"{season}|{split}"
    df["_season"] = str(season)
    df["_split"] = split
    df["_scope"] = scope
    return load_dataframe(conn, table, df, scope_column="_scope", scope_value=scope)


# --------------------------------------------------------------------------
# Projection snapshot history (append-only, change-detected)
# --------------------------------------------------------------------------


def _projection_value_hash(row: dict) -> str:
    """md5 of the row's projected values (every non-bookkeeping column). The
    change-detection signal — a new snapshot is appended only when this
    differs from the key's last stored hash."""
    payload = {k: v for k, v in row.items() if not str(k).startswith("_")}
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.md5(blob.encode()).hexdigest()  # noqa: S324 — not security, just a diff key


def _projection_rows(system: str, stat_group: str, horizon: str, captured: str) -> list[dict]:
    rows = _fg_call(fg.get_projections, system, stat_group)
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        playerid = row.get("playerid")
        if playerid is None or str(playerid) == "":
            continue  # no id -> cannot track this row's history
        key = str(playerid)
        if key in seen:
            continue  # one row per player per system; guard a stray dup
        seen.add(key)
        out.append(
            {
                **row,
                "_projection_system": system,
                "_stat_group": stat_group,
                "_horizon": horizon,
                "_captured_date": captured,
                "_row_hash": _projection_value_hash(row),
            }
        )
    return out


def _latest_projection_hashes(conn: psycopg.Connection) -> dict[tuple[str, str, str], str]:
    """Most recently stored ``_row_hash`` per ``(system, stat_group, playerid)``.
    ``{}`` on a fresh database where the table does not exist yet — the same
    "not bootstrapped, not an error" treatment as ``season_already_loaded``."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (PROJECTION_TABLE,))
        (exists,) = fetch_one(cur)
        if not exists:
            return {}
        cur.execute(
            "SELECT DISTINCT ON (_projection_system, _stat_group, playerid) "
            "_projection_system, _stat_group, playerid, _row_hash "
            f"FROM {PROJECTION_TABLE} "  # noqa: S608 — PROJECTION_TABLE is a module constant
            "ORDER BY _projection_system, _stat_group, playerid, "
            "_captured_date DESC, _loaded_at DESC"
        )
        return {(s, g, str(p)): h for s, g, p, h in cur.fetchall()}


def _changed_projection_rows(
    rows: list[dict], known: dict[tuple[str, str, str], str]
) -> list[dict]:
    return [
        r
        for r in rows
        if known.get((r["_projection_system"], r["_stat_group"], str(r["playerid"])))
        != r["_row_hash"]
    ]


def _load_projections(conn: psycopg.Connection) -> dict[str, int]:
    """One projection snapshot pass. Appends only changed/new keys."""
    captured = datetime.now(UTC).date().isoformat()
    known = _latest_projection_hashes(conn)
    systems = [(s, "preseason") for s in PRESEASON_SYSTEMS] + [(s, "ros") for s in ROS_SYSTEMS]
    appended = 0
    for system, horizon in systems:
        for stat_group in PROJECTION_STAT_GROUPS:
            label = f"{PROJECTION_TABLE} {system}/{stat_group}"
            try:
                rows = _projection_rows(system, stat_group, horizon, captured)
                new_rows = _changed_projection_rows(rows, known)
                if not new_rows:
                    continue
                df = _frame(new_rows)
                # Projection systems genuinely carry different column sets
                # (RoS systems have no quantile/uncertainty columns; each
                # system evolves its own set) — cross-system variation is
                # expected, not "drift" to warn about on every run.
                appended += append_dataframe(
                    conn,
                    PROJECTION_TABLE,
                    df,
                    identity_columns=_PROJECTION_IDENTITY,
                    schema_drift_policy="ignore",
                )
                conn.commit()
            except Exception as exc:  # noqa: BLE001 — logged + skipped, per-system isolation
                conn.rollback()
                print(f"fangraphs: {label} failed ({exc}); skipping")
    return {PROJECTION_TABLE: appended}


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def _season_range(first_year: int, current_year: int) -> range:
    return range(first_year, current_year + 1)


def bootstrap() -> dict[str, int]:
    current = date.today().year
    totals: dict[str, int] = {}
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        for table, stat_group in LEADERBOARDS:
            for season in _season_range(LEADERBOARD_FIRST_YEAR, current):
                if season < current and season_already_loaded(conn, table, season):
                    continue
                totals[table] = totals.get(table, 0) + _run_unit(
                    conn, f"{table} {season}", _load_leaderboard, table, stat_group, season
                )

        totals["raw.fangraphs_guts"] = _run_unit(conn, "raw.fangraphs_guts", _load_guts)

        for season in _season_range(PARK_FACTOR_FIRST_YEAR, current):
            totals["park_factors"] = totals.get("park_factors", 0) + _run_unit(
                conn, f"park factors {season}", _load_park_factors, season
            )

        for season in _season_range(PROSPECT_FIRST_YEAR, current):
            prospects = _run_unit(conn, f"prospects {season}", _load_prospects, season)
            totals["raw.fangraphs_prospects"] = totals.get("raw.fangraphs_prospects", 0) + prospects

        for table, position in SPLIT_BOARDS:
            for season in _season_range(SPLIT_FIRST_YEAR, current):
                for split in CURATED_SPLITS:
                    totals[table] = totals.get(table, 0) + _run_unit(
                        conn,
                        f"{table} {season} {split}",
                        _load_split_board,
                        table,
                        position,
                        season,
                        split,
                    )

        for table, count in _load_projections(conn).items():
            totals[table] = totals.get(table, 0) + count

        result["rows"] = sum(totals.values())
    return totals


def update() -> dict[str, int]:
    current = date.today().year
    totals: dict[str, int] = {}
    with get_connection() as conn, track_run(conn, SOURCE, "update") as result:
        for table, stat_group in LEADERBOARDS:
            totals[table] = _run_unit(
                conn, f"{table} {current}", _load_leaderboard, table, stat_group, current
            )

        totals["raw.fangraphs_guts"] = _run_unit(conn, "raw.fangraphs_guts", _load_guts)
        totals["park_factors"] = _run_unit(
            conn, f"park factors {current}", _load_park_factors, current
        )
        totals["raw.fangraphs_prospects"] = _run_unit(
            conn, f"prospects {current}", _load_prospects, current
        )

        for table, position in SPLIT_BOARDS:
            for split in CURATED_SPLITS:
                totals[table] = totals.get(table, 0) + _run_unit(
                    conn,
                    f"{table} {current} {split}",
                    _load_split_board,
                    table,
                    position,
                    current,
                    split,
                )

        for table, count in _load_projections(conn).items():
            totals[table] = totals.get(table, 0) + count

        result["rows"] = sum(totals.values())
    return totals


def health_check() -> list[Check]:
    return [
        check_table_has_rows("raw.fangraphs_batting"),
        check_table_has_rows("raw.fangraphs_pitching"),
        check_table_has_rows("raw.fangraphs_fielding"),
        check_table_has_rows("raw.fangraphs_guts"),
        check_table_has_rows("raw.fangraphs_park_factors"),
        check_table_has_rows(PROJECTION_TABLE),
        check_last_run(SOURCE),
        check_recent_run(SOURCE, FRESHNESS_THRESHOLD_MINUTES, mode="update"),
    ]
