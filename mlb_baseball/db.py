import psycopg

from mlb_baseball.config import database_url

# Session-level performance settings for the heavy, run-alone batch rebuilds
# (`mlb conform`, `mlb predict`). Plain `SET`, not `SET LOCAL`: these jobs
# commit between stages, and the settings must survive those commits for the
# whole short-lived connection.
#
#   - synchronous_commit=off: a full rebuild from a reproducible source
#     (raw -> core -> gold); a crash just means re-run, so trading last-few-
#     transactions durability for a large write-throughput win is safe here.
#   - work_mem: the point-in-time enrichment queries do big sorts/hashes that
#     spill to disk at the cluster default -- fatal on this host's spinning
#     HDDs. 1GB is safe because these jobs hold the "exclusive" workflow lock,
#     so only one runs at a time (unlike the 5-minute ingestion cron or a test
#     run, which must NOT get this and could otherwise OOM under concurrency).
#   - maintenance_work_mem: faster index maintenance during the rebuild.
_BATCH_SESSION_SETTINGS: dict[str, str] = {
    "synchronous_commit": "off",
    "work_mem": "1GB",
    "maintenance_work_mem": "4GB",
}


def get_connection() -> psycopg.Connection:
    return psycopg.connect(database_url())


def apply_batch_session_settings(conn: psycopg.Connection) -> None:
    """Apply `_BATCH_SESSION_SETTINGS` to `conn`. Call once, right after
    opening the connection, from `mlb conform` / `mlb predict` only -- never
    from the ingestion cron or the test suite (see the constant's docstring)."""
    with conn.cursor() as cur:
        for name, value in _BATCH_SESSION_SETTINGS.items():
            # name/value are module constants, not user input; psycopg can't
            # parameterize a SET target anyway.
            cur.execute(f"SET {name} = '{value}'")


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
