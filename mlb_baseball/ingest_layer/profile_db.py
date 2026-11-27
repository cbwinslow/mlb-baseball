"""Propose declared types for existing all-text tables by profiling the database (read-only).

For each text column of a ``raw`` table: count the non-empty values and how many fit each
candidate type, on a sample for big tables. Narrowest type that holds EVERY sampled value
wins; the proposal is a starting point, because a sample cannot prove a rare bad value is
absent. The full-scan check before any conversion does (``verify_cast``).
"""

import psycopg
from psycopg import sql

from mlb_baseball.ingest_layer.infer import _DATE, _FLOAT, _INT, _INT32, _TIMESTAMPTZ

_NUMBER = f"{_INT}|{_FLOAT}"
SAMPLE_ROWS = 200_000


def text_tables(conn: psycopg.Connection, schema: str = "raw") -> list[tuple[str, int, int]]:
    """``(table, estimated rows, size bytes)`` for ordinary tables with at least one text column."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, c.reltuples::bigint, pg_total_relation_size(c.oid)
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s AND c.relkind IN ('r', 'p')
              AND NOT EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhrelid = c.oid)
              AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attnum > 0
                          AND NOT a.attisdropped AND a.atttypid = 'text'::regtype)
            ORDER BY c.relname
            """,
            (schema,),
        )
        return [(r[0], r[1], r[2]) for r in cur.fetchall()]


def _text_columns(conn: psycopg.Connection, schema: str, table: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = %s "
            "AND table_name = %s AND data_type = 'text' ORDER BY ordinal_position",
            (schema, table),
        )
        return [r[0] for r in cur.fetchall()]


_CHUNK = 150  # columns per query: 8 aggregates each must stay under PostgreSQL's 1664 targets


def profile_table(
    conn: psycopg.Connection, table: str, rows: int, schema: str = "raw"
) -> dict[str, dict]:
    """``{column: {kind, non_empty, sampled}}`` for the table's text columns."""
    cols = _text_columns(conn, schema, table)
    out: dict[str, dict] = {}
    for start in range(0, len(cols), _CHUNK):
        out |= _profile_columns(conn, table, rows, cols[start : start + _CHUNK], schema)
    return out


def _profile_columns(
    conn: psycopg.Connection, table: str, rows: int, cols: list[str], schema: str
) -> dict[str, dict]:
    pct = min(100.0, max(0.01, SAMPLE_ROWS * 100.0 / max(rows, 1)))
    source = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(table))
    if pct < 100:
        source += sql.SQL(" TABLESAMPLE SYSTEM ({})").format(sql.Literal(pct))
    parts: list[sql.Composable] = []
    for c in cols:
        i = sql.Identifier(c)
        parts += [
            sql.SQL("count(*) FILTER (WHERE {c} IS NOT NULL AND {c} <> '')").format(c=i),
            sql.SQL("count(*) FILTER (WHERE {c} ~ {p})").format(c=i, p=sql.Literal(_INT)),
            sql.SQL("count(*) FILTER (WHERE {c} ~ {p})").format(c=i, p=sql.Literal(_NUMBER)),
            sql.SQL("count(*) FILTER (WHERE {c} ~ {p})").format(c=i, p=sql.Literal(_DATE)),
            sql.SQL("count(*) FILTER (WHERE {c} ~ {p})").format(c=i, p=sql.Literal(_TIMESTAMPTZ)),
            sql.SQL(
                "max(CASE WHEN {c} ~ {p} AND length({c}) < 19 THEN abs({c}::bigint) END)"
            ).format(c=i, p=sql.Literal(_INT)),
            sql.SQL("max(length({c}))").format(c=i),
            sql.SQL("count(*) FILTER (WHERE {c} ~ '^-?[0-9]+\\.0+$')").format(c=i),
        ]
    query = sql.SQL("SELECT count(*), {} FROM {}").format(sql.SQL(", ").join(parts), source)
    with conn.cursor() as cur:
        cur.execute(query)
        row = cur.fetchone() or ()
    sampled = int(row[0])
    out: dict[str, dict] = {}
    for n, c in enumerate(cols):
        non_empty, ints, nums, dates, stamps, biggest, _maxlen, whole = row[1 + 8 * n : 9 + 8 * n]
        if non_empty == 0:
            kind = "text"
        elif ints == non_empty:
            kind = "integer" if (biggest or 0) <= _INT32 else "bigint"
            if non_empty and biggest is None:
                kind = "text"  # integers too long for bigint
        elif nums == non_empty and whole == non_empty:
            kind = "integer?"  # every value is N.0: ints that pandas wrote as floats; review
        elif nums == non_empty:
            kind = "double precision"
        elif dates == non_empty:
            kind = "date"
        elif stamps == non_empty:
            kind = "timestamptz"
        else:
            kind = "text"
        out[c] = {"kind": kind, "non_empty": int(non_empty), "sampled": sampled}
    return out


def verify_cast(
    conn: psycopg.Connection, table: str, column: str, kind: str, schema: str = "raw"
) -> int:
    """Full scan: how many non-empty values do NOT fit ``kind``. Zero is the only safe answer."""
    pattern = {
        "integer": _INT,
        "bigint": _INT,
        "double precision": _NUMBER,
        "date": _DATE,
        "timestamptz": _TIMESTAMPTZ,
    }[kind]
    query = sql.SQL(
        "SELECT count(*) FROM {}.{} WHERE {c} IS NOT NULL AND {c} <> '' AND {c} !~ {p}"
    ).format(
        sql.Identifier(schema),
        sql.Identifier(table),
        c=sql.Identifier(column),
        p=sql.Literal(pattern),
    )
    with conn.cursor() as cur:
        cur.execute(query)
        return int((cur.fetchone() or (0,))[0])
