"""gold.fangraphs_guts -- fangraphs-conform Beat 1 (ADR-290).

Verbatim numeric conform of raw.fangraphs_guts (FanGraphs' Guts! per-season
wOBA / FIP constants). Verifies a 1:1 value map, idempotency, and a clean skip
when the raw source was never ingested.

raw.fangraphs_guts is created on demand by the connector (no migration owns
it), so this file creates it -- same convention as test_fangraphs_load.py.
"""

from decimal import Decimal

from mlb_baseball import report

_GUTS_COLS = (
    "season",
    "woba",
    "wobascale",
    "wbb",
    "whbp",
    "w1b",
    "w2b",
    "w3b",
    "whr",
    "runsb",
    "runcs",
    "r_pa",
    "r_w",
    "cfip",
)


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.fangraphs_guts")
        cur.execute("TRUNCATE gold.fangraphs_guts")
    db_conn.commit()


def _create_raw(db_conn, rows):
    with db_conn.cursor() as cur:
        cols_ddl = ", ".join(f"{c} text" for c in _GUTS_COLS)
        cur.execute(
            f"CREATE TABLE raw.fangraphs_guts ({cols_ddl}, _loaded_at timestamptz DEFAULT now())"
        )
        placeholders = ", ".join(["%s"] * len(_GUTS_COLS))
        for row in rows:
            cur.execute(
                f"INSERT INTO raw.fangraphs_guts ({', '.join(_GUTS_COLS)}) VALUES ({placeholders})",
                tuple(row.get(c, "") for c in _GUTS_COLS),
            )
    db_conn.commit()


def _build(db_conn):
    count = report._build_backbone_relation(
        db_conn,
        "gold.fangraphs_guts",
        report._GOLD_FANGRAPHS_GUTS_SQL,
        source="raw.fangraphs_guts",
    )
    db_conn.commit()
    return count


# One row per season; values chosen to look like real FanGraphs Guts! output.
_ROWS = [
    {
        "season": "2015",
        "woba": "0.313",
        "wobascale": "1.251",
        "wbb": "0.687",
        "whbp": "0.718",
        "w1b": "0.881",
        "w2b": "1.256",
        "w3b": "1.594",
        "whr": "2.065",
        "runsb": "0.2",
        "runcs": "-0.410",
        "r_pa": "0.113",
        "r_w": "9.421",
        "cfip": "3.134",
    },
    {
        "season": "1968",
        "woba": "0.290",
        "wobascale": "1.212",
        "wbb": "0.663",
        "whbp": "0.694",
        "w1b": "0.855",
        "w2b": "1.225",
        "w3b": "1.560",
        "whr": "2.020",
        "runsb": "0.2",
        "runcs": "-0.393",
        "r_pa": "0.098",
        "r_w": "8.117",
        "cfip": "3.049",
    },
]


def test_guts_conforms_every_column_verbatim_as_numeric(db_conn):
    _reset(db_conn)
    _create_raw(db_conn, _ROWS)

    assert _build(db_conn) == 2

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT {', '.join(_GUTS_COLS)} FROM gold.fangraphs_guts ORDER BY season")
        got = {r[0]: dict(zip(_GUTS_COLS, r, strict=True)) for r in cur.fetchall()}

    assert set(got) == {1968, 2015}
    for raw_row in _ROWS:
        season = int(raw_row["season"])
        for col in _GUTS_COLS[1:]:
            assert got[season][col] == Decimal(raw_row[col]), (season, col)

    _reset(db_conn)


def test_guts_build_is_idempotent(db_conn):
    _reset(db_conn)
    _create_raw(db_conn, _ROWS)

    assert _build(db_conn) == 2
    assert _build(db_conn) == 2

    with db_conn.cursor() as cur:
        cur.execute("SELECT season, woba FROM gold.fangraphs_guts ORDER BY season")
        assert cur.fetchall() == [(1968, Decimal("0.290")), (2015, Decimal("0.313"))]

    _reset(db_conn)


def test_guts_build_skips_cleanly_without_the_raw_source(db_conn):
    _reset(db_conn)  # no raw.fangraphs_guts created

    # Pre-seed a stale gold row to prove the skip does not TRUNCATE it away.
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO gold.fangraphs_guts (season, woba) VALUES (1999, 0.301)")
    db_conn.commit()

    assert _build(db_conn) == 0

    with db_conn.cursor() as cur:
        cur.execute("SELECT season, woba FROM gold.fangraphs_guts")
        assert cur.fetchall() == [(1999, Decimal("0.301"))]

    _reset(db_conn)
