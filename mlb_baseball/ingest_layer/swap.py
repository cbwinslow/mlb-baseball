"""Replace an all-text table with its typed version, safely (openspec typed-raw-layer D3a).

The typed table is loaded beside the old one as ``<table>__new``; ``compare`` lists every
difference cell by cell; ``swap`` renames in ONE transaction (old -> ``__old``, new -> the
real name) and keeps ``__old`` until the owner approves dropping it. Rolling back is the same
two renames reversed.
"""

from dataclasses import dataclass

import psycopg
from psycopg import sql

from mlb_baseball.market_store import MarketTable


@dataclass(frozen=True)
class Difference:
    table: str
    old_rows: int
    new_rows: int
    only_old: int  # rows in the old table with no equal row in the new one
    only_new: int

    @property
    def same(self) -> bool:
        return self.old_rows == self.new_rows and self.only_old == 0 and self.only_new == 0


def _old_side(col: str, kind: str) -> sql.Composable:
    ident = sql.Identifier(col)
    if kind == "double precision":  # '2.00' and 2 are the same number
        return sql.SQL("NULLIF({}::text, '')::double precision").format(ident)
    if kind in ("integer", "bigint"):  # the old pandas path wrote 1934 as '1934.0'
        return sql.SQL("regexp_replace({}::text, '\\.0+$', '')").format(ident)
    return sql.SQL("{}::text").format(ident)


def _new_side(col: str, kind: str, null_old: tuple[str, ...]) -> sql.Composable:
    ident = sql.Identifier(col)
    if kind == "double precision":
        return sql.SQL("{}::double precision").format(ident)
    if not null_old:
        return sql.SQL("{}::text").format(ident)
    values = sql.SQL(", ").join(sql.Literal(v) for v in null_old)
    # the old path turned these source texts into NULL; map ours the same way to compare the rest
    return sql.SQL("CASE WHEN {c}::text IN ({v}) THEN NULL ELSE {c}::text END").format(
        c=ident, v=values
    )


def compare(
    conn: psycopg.Connection,
    old: str,
    new: str,
    spec: MarketTable,
    *,
    null_old: tuple[str, ...] = ("NA",),
) -> Difference:
    """Cell-by-cell comparison of the columns both tables share. ``null_old`` lists source
    texts the old loader stored as NULL (a known corruption); they are treated as equal."""
    kinds = {c.name: c.kind for c in spec.columns}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s",
            tuple(old.split(".")),
        )
        have_old = {r[0] for r in cur.fetchall()}
        cols = [c for c in kinds if c in have_old]
        old_sel = sql.SQL(", ").join(_old_side(c, kinds[c]) for c in cols)
        new_sel = sql.SQL(", ").join(_new_side(c, kinds[c], null_old) for c in cols)
        o, n = sql.Identifier(*old.split(".")), sql.Identifier(*new.split("."))

        def count(
            a: sql.Composable, b: sql.Composable, left: sql.Identifier, right: sql.Identifier
        ):
            cur.execute(
                sql.SQL(
                    "SELECT count(*) FROM (SELECT {a} FROM {l} EXCEPT ALL SELECT {b} FROM {r}) x"
                ).format(a=a, b=b, l=left, r=right)
            )
            return cur.fetchone()[0]  # type: ignore[index]

        only_old = count(old_sel, new_sel, o, n)
        only_new = count(new_sel, old_sel, n, o)
        cur.execute(
            sql.SQL("SELECT (SELECT count(*) FROM {}), (SELECT count(*) FROM {})").format(o, n)
        )
        old_rows, new_rows = cur.fetchone()  # type: ignore[misc]
    return Difference(old, old_rows, new_rows, only_old, only_new)


def swap(conn: psycopg.Connection, table: str) -> None:
    """Rename ``table`` -> ``table__old`` and ``table__new`` -> ``table`` in one transaction.
    The caller commits (or rolls everything back)."""
    schema, _, rel = table.partition(".")
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("ALTER TABLE {} RENAME TO {}").format(
                sql.Identifier(schema, rel), sql.Identifier(rel + "__old")
            )
        )
        cur.execute(
            sql.SQL("ALTER TABLE {} RENAME TO {}").format(
                sql.Identifier(schema, rel + "__new"), sql.Identifier(rel)
            )
        )
