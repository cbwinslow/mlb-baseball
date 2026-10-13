"""Typed, append-only landing for the market price tables (spec market-price-store).

One job: take source rows as CSV text, check each value against the column's type, put
rows that fail into the table's reject table (as source text, never lost), and insert the
rest with ``ON CONFLICT DO NOTHING``. Fetching, paging and the ingestion ledger stay in the
connectors; table creation and engine choice (TimescaleDB hypertable or plain table) stay
in migration 0117's ``meta.create_market_tables``. This module knows neither.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import psycopg
from psycopg import sql

_INTEGER = r"^[0-9]{1,9}$"
_BIGINT = r"^[0-9]{1,18}$"
_FLOAT = r"^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$"


@dataclass(frozen=True)
class Column:
    """A typed column. ``kind`` is a PostgreSQL type name; ``digits`` bounds the integer
    part of a ``numeric(p, s)`` so an out-of-range value is rejected, not an error."""

    name: str
    kind: str = "text"
    nullable: bool = True
    digits: int = 0

    def pattern(self) -> str | None:
        if self.kind == "integer":
            return _INTEGER
        if self.kind == "bigint":
            return _BIGINT
        if self.kind == "double precision":
            return _FLOAT
        if self.kind.startswith("numeric"):
            return rf"^-?[0-9]{{1,{self.digits}}}(\.[0-9]+)?$"
        return None


@dataclass(frozen=True)
class MarketTable:
    """``columns`` are the typed columns; any other column in an incoming batch is a new
    source field and is stored as text (source-faithful)."""

    name: str
    reject: str
    columns: tuple[Column, ...]
    key: tuple[str, ...]
    reject_source_row: bool = False  # True: reject keeps the whole row as jsonb

    def typed(self) -> dict[str, Column]:
        return {c.name: c for c in self.columns}


POLYMARKET_PRICE = MarketTable(
    name="raw.polymarket_price",
    reject="raw.polymarket_price_reject",
    columns=(
        Column("clob_token_id", nullable=False),
        Column("_market", "integer"),
        Column("_event", "integer"),
        Column("ts", "bigint", nullable=False),
        Column("price", "double precision"),
    ),
    key=("clob_token_id", "ts"),
)

_KALSHI_PRICE_COLUMNS = (
    "yes_bid_close_dollars yes_bid_high_dollars yes_bid_low_dollars yes_bid_open_dollars "
    "yes_ask_close_dollars yes_ask_high_dollars yes_ask_low_dollars yes_ask_open_dollars "
    "price_close_dollars price_high_dollars price_low_dollars price_mean_dollars "
    "price_open_dollars price_previous_dollars price_close price_high price_low price_mean "
    "price_open price_previous yes_bid_close yes_bid_high yes_bid_low yes_bid_open "
    "yes_ask_close yes_ask_high yes_ask_low yes_ask_open"
).split()

KALSHI_CANDLE = MarketTable(
    name="raw.kalshi_candle",
    reject="raw.kalshi_candle_reject",
    columns=(
        Column("ticker", nullable=False),
        Column("ts", "bigint", nullable=False),
        Column("open_interest", "numeric(14,2)", digits=12),
        Column("volume", "numeric(14,2)", digits=12),
        *(Column(name, "numeric(10,4)", digits=6) for name in _KALSHI_PRICE_COLUMNS),
    ),
    key=("ticker", "ts"),
    reject_source_row=True,
)


def ensure_store(conn: psycopg.Connection) -> None:
    """Create the typed tables if absent (a no-op when they exist) and commit."""
    with conn.cursor() as cur:
        cur.execute("SELECT meta.create_market_tables('')")
    conn.commit()


def add_text_columns(conn: psycopg.Connection, table: MarketTable, names: Sequence[str]) -> None:
    """Add source fields the table does not have yet as nullable text, and commit."""
    with conn.cursor() as cur:
        for name in names:
            cur.execute(
                sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} text").format(
                    sql.SQL(table.name), sql.Identifier(name)
                )
            )
    conn.commit()


def missing_columns(
    conn: psycopg.Connection, table: MarketTable, names: Sequence[str]
) -> list[str]:
    schema, _, rel = table.name.partition(".")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s",
            (schema, rel),
        )
        have = {name for (name,) in cur.fetchall()}
    return [n for n in names if n not in have]


def _reason_sql(table: MarketTable, columns: Sequence[str]) -> sql.Composable:
    """A CASE expression naming the first column of the row that fails its type check."""
    typed = table.typed()
    whens: list[sql.Composable] = []
    for name in columns:
        col = typed.get(name)
        if col is None:
            continue
        ident = sql.Identifier(name)
        if not col.nullable:
            whens.append(
                sql.SQL("WHEN NULLIF({c}, '') IS NULL THEN {msg}").format(
                    c=ident, msg=sql.Literal(f"{name} is empty")
                )
            )
        pattern = col.pattern()
        if pattern:
            whens.append(
                sql.SQL("WHEN NULLIF({c}, '') IS NOT NULL AND {c} !~ {p} THEN {msg}").format(
                    c=ident,
                    p=sql.Literal(pattern),
                    msg=sql.Literal(f"{name} is not a valid {col.kind}"),
                )
            )
    if not whens:
        return sql.SQL("NULL")
    return sql.SQL("CASE {} END").format(sql.SQL(" ").join(whens))


def append_rows(
    conn: psycopg.Connection, table: MarketTable, columns: Sequence[str], csv_text: str
) -> tuple[int, int]:
    """Land CSV rows (no header, ``columns`` order) and return ``(inserted, rejected)``.

    Values are staged as text, checked, cast and inserted with ``ON CONFLICT DO NOTHING``,
    so a second load of the same rows inserts nothing. A row with an empty source value
    stores NULL for it, never zero. A row failing a check goes to the reject table.
    Columns missing from the table must be added first (:func:`add_text_columns`).
    """
    if not csv_text:
        return 0, 0
    typed = table.typed()
    cols = [sql.Identifier(c) for c in columns]
    casts = [
        sql.SQL("NULLIF({c}, '')::{kind}").format(c=sql.Identifier(c), kind=sql.SQL(typed[c].kind))
        if c in typed and typed[c].kind != "text"
        else sql.SQL("NULLIF({c}, '')").format(c=sql.Identifier(c))
        for c in columns
    ]
    stage = sql.Identifier(table.name.split(".")[-1] + "_stage")  # one per table: shapes differ
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("CREATE TEMP TABLE IF NOT EXISTS {s} ({defs}, _reason text)").format(
                s=stage, defs=sql.SQL(", ").join(sql.SQL("{} text").format(c) for c in cols)
            )
        )
        cur.execute(sql.SQL("TRUNCATE {}").format(stage))
        with cur.copy(
            sql.SQL("COPY {s} ({c}) FROM STDIN WITH (FORMAT csv)").format(
                s=stage, c=sql.SQL(", ").join(cols)
            )
        ) as copy:
            copy.write(csv_text)
        cur.execute(
            sql.SQL("UPDATE {s} SET _reason = {reason}").format(
                s=stage, reason=_reason_sql(table, columns)
            )
        )
        rejected = _write_rejects(cur, table, columns, stage)
        cur.execute(
            sql.SQL(
                "INSERT INTO {t} ({c}) SELECT {casts} FROM {s} WHERE _reason IS NULL "
                "ON CONFLICT DO NOTHING"
            ).format(
                t=sql.SQL(table.name),
                c=sql.SQL(", ").join(cols),
                casts=sql.SQL(", ").join(casts),
                s=stage,
            )
        )
        inserted = cur.rowcount
        cur.execute(sql.SQL("TRUNCATE {}").format(stage))
    return inserted, rejected


def _write_rejects(
    cur: psycopg.Cursor, table: MarketTable, columns: Sequence[str], stage: sql.Identifier
) -> int:
    if table.reject_source_row:
        cur.execute(
            sql.SQL(
                "INSERT INTO {r} (ticker, ts, source_row, reason) "
                "SELECT ticker, ts, to_jsonb(s) - '_reason', _reason FROM {s} s "
                "WHERE _reason IS NOT NULL"
            ).format(r=sql.SQL(table.reject), s=stage)
        )
    else:
        names = [c for c in columns if c in {"clob_token_id", "_market", "_event", "ts", "price"}]
        idents = sql.SQL(", ").join(sql.Identifier(c) for c in names)
        cur.execute(
            sql.SQL(
                "INSERT INTO {r} ({names}, reason) SELECT {names}, _reason FROM {s} "
                "WHERE _reason IS NOT NULL"
            ).format(r=sql.SQL(table.reject), names=idents, s=stage)
        )
    return cur.rowcount
