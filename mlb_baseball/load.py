"""Generic loader for pandas-DataFrame-shaped sources (pybaseball-backed connectors).

Complements the CSV+COPY pattern used by connectors that fetch raw text directly
(e.g. chadwick_register). Table schema is derived from the DataFrame itself rather
than a hand-written migration — impractical to hand-author migrations for the ~27
Lahman tables individually, and pandas is already the source of truth for their
shape. See docs/ARCHITECTURE.md "Loading patterns".
"""

import re
import warnings
from typing import Literal

import pandas as pd
import psycopg
from psycopg import sql

_IDENTIFIER_RE = re.compile(r"[^a-z0-9_]")


class SchemaDriftWarning(UserWarning):
    """A source batch's column set differs from its landed raw table."""


class SchemaDriftError(ValueError):
    """A connector policy requires explicit review before accepting drift."""


def _pg_column_name(name: str) -> str:
    """Postgres-idiomatic column name: lowercased, non-alphanumeric stripped, and
    prefixed if it would otherwise start with a digit (e.g. Lahman's "2B"/"3B"
    columns). Case-folding only — no semantic change from the source
    (e.g. playerID -> playerid)."""
    if not isinstance(name, str):
        raise ValueError(f"source column name must be text, got {name!r}")
    cleaned = _IDENTIFIER_RE.sub("_", name.lower())
    if not cleaned.strip("_"):
        raise ValueError(f"source column name sanitizes to empty: {name!r}")
    return f"n{cleaned}" if cleaned[0].isdigit() else cleaned


def _pg_column_names(df: pd.DataFrame) -> list[str]:
    columns = [_pg_column_name(name) for name in df.columns]
    duplicates = sorted({column for column in columns if columns.count(column) > 1})
    if duplicates:
        raise ValueError(f"source columns collide after Postgres sanitization: {duplicates}")
    return columns


def _table_identifier(table: str) -> sql.Identifier:
    return sql.Identifier(*table.split("."))


def _ensure_table_and_columns(
    cur: psycopg.Cursor, table: str, table_ident: sql.Identifier, columns: list[str]
) -> None:
    """Creates `table` if needed (schema derived from the caller's columns) and adds
    any column present in `columns` but not yet on the table. Shared by
    load_dataframe (replace semantics) and append_dataframe (pure-insert semantics)
    since both need the identical "make sure the table can hold this DataFrame"
    step before deciding what to do about existing rows.

    Column identifiers are always quoted (via psycopg.sql.Identifier) — raw sources
    sometimes use reserved SQL keywords as column names (e.g. Retrosheet's
    parkcode.txt has a column literally named "end"; found by actually running
    this against real data, not by inspection).

    A later call's DataFrame can have columns an earlier one didn't — e.g.
    retrosheet_box.py's game rows come from cwbox's XML output, which only
    includes attributes actually present for a given game (some historical
    games have extra umpire positions others don't), so different years'
    DataFrames can genuinely differ in shape. Missing columns are added via
    ALTER TABLE rather than failing on COPY; found by a real bootstrap
    crashing partway through on "column ... does not exist", not designed
    in advance."""
    column_defs = sql.SQL(", ").join(sql.SQL("{} text").format(sql.Identifier(c)) for c in columns)
    cur.execute(
        sql.SQL(
            "CREATE TABLE IF NOT EXISTS {table} "
            "({column_defs}, _loaded_at timestamptz NOT NULL DEFAULT now())"
        ).format(table=table_ident, column_defs=column_defs)
    )
    schema, bare_table = table.split(".")
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s",
        (schema, bare_table),
    )
    existing_columns = {row[0] for row in cur.fetchall()}
    for column in columns:
        if column not in existing_columns:
            cur.execute(
                sql.SQL("ALTER TABLE {table} ADD COLUMN {col} text").format(
                    table=table_ident, col=sql.Identifier(column)
                )
            )


def _check_schema_drift(
    cur: psycopg.Cursor,
    table: str,
    columns: list[str],
    policy: Literal["ignore", "warn", "error"],
) -> None:
    if policy == "ignore":
        return
    schema, bare_table = table.split(".")
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s",
        (schema, bare_table),
    )
    existing = {row[0] for row in cur.fetchall()} - {"_loaded_at"}
    if not existing:
        return
    incoming = set(columns)
    added, removed = sorted(incoming - existing), sorted(existing - incoming)
    if not added and not removed:
        return
    message = f"{table}: source schema drift (added={added}, removed={removed})"
    if policy == "error":
        raise SchemaDriftError(message)
    warnings.warn(message, SchemaDriftWarning, stacklevel=3)


def _copy_dataframe(cur: psycopg.Cursor, table_ident: sql.Identifier, df: pd.DataFrame) -> int:
    columns = _pg_column_names(df)
    csv_text = df.to_csv(index=False, header=False)
    column_list = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
    copy_sql = sql.SQL("COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv)").format(
        table=table_ident, columns=column_list
    )
    with cur.copy(copy_sql) as copy:
        copy.write(csv_text)
    return cur.rowcount


def load_dataframe(
    conn: psycopg.Connection,
    table: str,
    df: pd.DataFrame,
    *,
    scope_column: str | None = None,
    scope_value: str | None = None,
    schema_drift_policy: Literal["ignore", "warn", "error"] = "warn",
) -> int:
    """Creates `table` if needed (schema derived from df's columns) and loads df into
    it. Default replace strategy is a full TRUNCATE — right for sources small enough
    to reload whole (the register, Lahman). For sources landed in independent chunks
    (e.g. Retrosheet, one season at a time), pass scope_column/scope_value to replace
    only rows matching that value, leaving every other chunk's data alone — a full
    TRUNCATE on every call would wipe out all previously loaded seasons.
    scope_column must already be a sanitized column name (e.g. "_season").

    When scope_column is given, an index on it is created (once, IF NOT EXISTS)
    right after the table — otherwise every per-chunk DELETE is a full sequential
    scan, and gets slower as the table grows. Found the hard way: retrosheet's
    bootstrap looked "stuck" partway through — it wasn't, a DELETE against a
    9GB, un-indexed raw.retrosheet_plays was just taking longer each year.

    For pure event-stream data with no natural "chunk" to replace (e.g. a live-game
    snapshot, captured repeatedly and meant to accumulate, never overwritten), use
    append_dataframe instead."""
    columns = _pg_column_names(df)
    table_ident = _table_identifier(table)
    with conn.cursor() as cur:
        _check_schema_drift(cur, table, columns, schema_drift_policy)
        _ensure_table_and_columns(cur, table, table_ident, columns)
        if scope_column is None:
            cur.execute(sql.SQL("TRUNCATE {table}").format(table=table_ident))
        else:
            index_name = f"{table.split('.')[-1]}_{scope_column}_idx"
            cur.execute(
                sql.SQL("CREATE INDEX IF NOT EXISTS {index} ON {table} ({col})").format(
                    index=sql.Identifier(index_name),
                    table=table_ident,
                    col=sql.Identifier(scope_column),
                )
            )
            cur.execute(
                sql.SQL("DELETE FROM {table} WHERE {col} = %s").format(
                    table=table_ident, col=sql.Identifier(scope_column)
                ),
                (scope_value,),
            )
        return _copy_dataframe(cur, table_ident, df)


def ensure_table(
    conn: psycopg.Connection, table: str, columns: list[str], *, index_column: str | None = None
) -> None:
    """Create ``table`` (all-text columns plus ``_loaded_at``) and an index on
    ``index_column`` if they are missing, and commit. Call once before several
    threads each call :func:`replace_dataframe_range`, so they do not race to
    create the table."""
    table_ident = _table_identifier(table)
    with conn.cursor() as cur:
        _ensure_table_and_columns(cur, table, table_ident, columns)
        if index_column is not None:
            cur.execute(
                sql.SQL("CREATE INDEX IF NOT EXISTS {index} ON {table} ({col})").format(
                    index=sql.Identifier(f"{table.split('.')[-1]}_{index_column}_idx"),
                    table=table_ident,
                    col=sql.Identifier(index_column),
                )
            )
    conn.commit()


def replace_dataframe_range(
    conn: psycopg.Connection,
    table: str,
    df: pd.DataFrame,
    *,
    key_column: str,
    keys: list[str],
    range_column: str,
    low: int,
    high: int,
) -> int:
    """Replace the rows of ``keys`` whose numeric ``range_column`` lies in
    ``[low, high)`` with ``df``, in the caller's transaction (the caller commits, so
    a ledger write can ride in the same transaction). For time-series items fetched
    one window at a time, where :func:`load_dataframe`'s whole-key replace would
    delete the other windows. The table must already exist (:func:`ensure_table`).
    A key with no rows in ``df`` still has its window cleared."""
    return replace_csv_range(
        conn,
        table,
        _pg_column_names(df),
        df.to_csv(index=False, header=False) if not df.empty else "",
        key_column=key_column,
        keys=keys,
        range_column=range_column,
        low=low,
        high=high,
    )


def replace_csv_range(
    conn: psycopg.Connection,
    table: str,
    columns: list[str],
    csv_text: str,
    *,
    key_column: str,
    keys: list[str],
    range_column: str,
    low: int,
    high: int,
) -> int:
    """Like :func:`replace_dataframe_range` for rows the caller already rendered as
    CSV text (no header) in ``columns`` order. Building the text directly is several
    times cheaper than ``DataFrame.to_csv`` and matters when many threads share one
    Python process (measured: 21 ms against 112 ms for 21,700 rows). Empty text only
    clears the window."""
    table_ident = _table_identifier(table)
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                "DELETE FROM {table} WHERE {key} = ANY(%s) "
                "AND {rng}::numeric >= %s AND {rng}::numeric < %s"
            ).format(
                table=table_ident,
                key=sql.Identifier(key_column),
                rng=sql.Identifier(range_column),
            ),
            (keys, low, high),
        )
        if not csv_text:
            return 0
        copy_sql = sql.SQL("COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv)").format(
            table=table_ident, columns=sql.SQL(", ").join(sql.Identifier(c) for c in columns)
        )
        with cur.copy(copy_sql) as copy:
            copy.write(csv_text)
        return cur.rowcount


def replace_dataframe_scopes(
    conn: psycopg.Connection,
    table: str,
    df: pd.DataFrame,
    *,
    scope_column: str,
    scope_values: list[str],
    schema_drift_policy: Literal["ignore", "warn", "error"] = "warn",
) -> int:
    """Replace several independent source items in one DELETE + COPY.

    This is the bulk counterpart to ``load_dataframe(..., scope_value=...)``.
    It is deliberately replace-by-item, rather than append, so a retry cannot
    duplicate a game and an empty successful response can still remove stale
    rows for that game.  The caller must provide every successfully fetched
    scope, including scopes whose parsed dataframe has zero rows.
    """
    if not scope_values:
        return 0
    columns = _pg_column_names(df)
    if df.empty and not columns:
        raise ValueError(f"{table}: an empty bulk replace still needs its source columns")
    table_ident = _table_identifier(table)
    with conn.cursor() as cur:
        _check_schema_drift(cur, table, columns, schema_drift_policy)
        _ensure_table_and_columns(cur, table, table_ident, columns)
        index_name = f"{table.split('.')[-1]}_{scope_column}_idx"
        cur.execute(
            sql.SQL("CREATE INDEX IF NOT EXISTS {index} ON {table} ({col})").format(
                index=sql.Identifier(index_name),
                table=table_ident,
                col=sql.Identifier(scope_column),
            )
        )
        cur.execute(
            sql.SQL("DELETE FROM {table} WHERE {col} = ANY(%s)").format(
                table=table_ident, col=sql.Identifier(scope_column)
            ),
            (scope_values,),
        )
        return _copy_dataframe(cur, table_ident, df) if not df.empty else 0


def upsert_dataframe(
    conn: psycopg.Connection,
    table: str,
    df: pd.DataFrame,
    *,
    key_column: str,
    schema_drift_policy: Literal["ignore", "warn", "error"] = "warn",
) -> int:
    """Replace only the rows whose ``key_column`` value appears in ``df``; rows the
    source stopped returning are kept. For catalog tables that must not lose
    history when a source drops an item (``_loaded_at`` then reads as "last seen").
    An empty ``df`` changes nothing. A null key is rejected: it cannot be
    matched on a later run, so such rows would pile up instead of being replaced."""
    if df.empty:
        return 0
    if df[key_column].isna().any():
        raise ValueError(f"{table}: null values in key column {key_column!r}")
    keys = sorted({str(value) for value in df[key_column]})
    return replace_dataframe_scopes(
        conn,
        table,
        df,
        scope_column=key_column,
        scope_values=keys,
        schema_drift_policy=schema_drift_policy,
    )


def append_dataframe(
    conn: psycopg.Connection,
    table: str,
    df: pd.DataFrame,
    *,
    identity_columns: tuple[str, ...],
    schema_drift_policy: Literal["ignore", "warn", "error"] = "warn",
) -> int:
    """Creates `table` if needed and inserts df's rows — never truncates, never
    deletes. For genuinely append-only event-stream data where every previously
    landed row stays meaningful (e.g. raw.mlb_live_game: each call captures one
    point-in-time snapshot of an in-progress game, and the whole point is keeping
    every snapshot, not just the latest). If the source instead has a natural
    "this chunk replaces that chunk" shape, use load_dataframe. Every append
    declares an immutable observation identity so unexplained duplicate rows
    cannot be mistaken for meaningful history."""
    columns = _pg_column_names(df)
    missing_identity = set(identity_columns) - set(columns)
    if not identity_columns or missing_identity:
        raise ValueError(
            f"{table}: append identity columns missing from batch: {sorted(missing_identity)}"
        )
    if df[list(identity_columns)].isnull().any().any():
        raise ValueError(f"{table}: append identity columns cannot be null")
    if df.duplicated(subset=list(identity_columns)).any():
        raise ValueError(f"{table}: duplicate append identity in one batch")
    table_ident = _table_identifier(table)
    with conn.cursor() as cur:
        _check_schema_drift(cur, table, columns, schema_drift_policy)
        _ensure_table_and_columns(cur, table, table_ident, columns)
        return _copy_dataframe(cur, table_ident, df)


def season_already_loaded(
    conn: psycopg.Connection, table: str, season: int | str, scope_column: str = "_season"
) -> bool:
    """For full-history bootstraps built from many independent per-season API
    calls (mlb_api.py, statcast.py) rather than Retrosheet's downloaded-file
    products (which already get disk-cached via manifest.py) — lets bootstrap()
    skip a past season that's already landed instead of re-fetching data that's
    published, complete, and will never change. Only meaningful for seasons
    before the current one; the caller is responsible for always re-fetching
    the current season, which is still in progress by definition. ``scope_column`` names
    another text column to test (``_scope`` for per-season-and-split boards); ``season``
    is then the value to look for."""
    # information_schema never raises on a missing table (it just returns no
    # rows), so this doubles as the table-existence check — no separate
    # UndefinedTable handling needed for the second query below.
    schema, bare_table = table.split(".")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s AND column_name = %s",
            (schema, bare_table, scope_column),
        )
        if cur.fetchone() is None:
            return False
        cur.execute(
            sql.SQL("SELECT 1 FROM {table} WHERE {column} = %s LIMIT 1").format(
                table=_table_identifier(table), column=sql.Identifier(scope_column)
            ),
            (str(season),),
        )
        return cur.fetchone() is not None
