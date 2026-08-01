import psycopg

from mlb_baseball.config import database_url


def get_connection() -> psycopg.Connection:
    return psycopg.connect(database_url())


def fetch_one(cur: psycopg.Cursor) -> tuple:
    """fetchone() for queries that always return exactly one row (count(*)/
    aggregates/RETURNING). psycopg types fetchone() as `tuple | None`, and the
    codebase unpacked it directly at ~25 sites — fine at runtime for these
    query shapes, but a None here (a logic bug) would surface as a TypeError
    several frames away. Raise with intent instead; callers whose queries can
    legitimately return no row keep using fetchone() and handling None."""
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("query expected to return exactly one row returned none")
    return row
