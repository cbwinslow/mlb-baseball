import psycopg

from mlb_baseball.config import database_url, load_settings


# Session-level performance settings for the heavy, run-alone batch rebuilds
# (`mlb conform`, `mlb predict`). Plain `SET`, not `SET LOCAL`: these jobs
# commit between stages, and the settings must survive those commits for the
# whole short-lived connection.
#
#   - synchronous_commit=off: a full rebuild from a reproducible source
#     (raw -> core -> gold); a crash just means re-run, so trading last-few-
#     transactions durability for a large write-throughput win is safe here.
#   - work_mem: the point-in-time enrichment queries do big sorts/hashes that
#     can spill to disk at the cluster default. On this project's own
#     production host (40 cores / 125 GB RAM, docs/DECISIONS.md), 1GB is
#     safe because these jobs hold the "exclusive" workflow lock, so only one
#     runs at a time (unlike the 5-minute ingestion cron or a test run, which
#     must NOT get this and could otherwise OOM under concurrency). This
#     project ships as code other people run on their own, possibly modest,
#     machines (openspec/project.md), so 1GB is NOT the default -- it comes
#     from config (`Settings.batch_work_mem`, issue #202) with a conservative
#     fallback, and this host's own mlb.toml opts into 1GB explicitly (see
#     mlb.toml.example).
#   - maintenance_work_mem: faster index maintenance during the rebuild; same
#     configurable-with-conservative-default treatment as work_mem.
def _batch_session_settings() -> dict[str, str]:
    """Read `Settings.batch_work_mem` / `batch_maintenance_work_mem` (env vars
    `MLB_BATCH_WORK_MEM` / `MLB_BATCH_MAINTENANCE_WORK_MEM`, or `[mlb]`
    `batch_work_mem` / `batch_maintenance_work_mem` in `mlb.toml`) and build
    this connection's batch session settings from them. Computed fresh per
    call (like `mlb_baseball.config.database_url`) rather than cached at
    import time, so an env var set after the module is imported still takes
    effect."""
    settings = load_settings()
    return {
        "synchronous_commit": "off",
        "work_mem": settings.batch_work_mem,
        "maintenance_work_mem": settings.batch_maintenance_work_mem,
    }


def get_connection() -> psycopg.Connection:
    return psycopg.connect(database_url())


def apply_batch_session_settings(conn: psycopg.Connection) -> None:
    """Apply `_batch_session_settings()` to `conn`. Call once, right after
    opening the connection, from `mlb conform` / `mlb predict` only -- never
    from the ingestion cron or the test suite (see the settings' docstring
    above)."""
    with conn.cursor() as cur:
        for name, value in _batch_session_settings().items():
            # name is a fixed set of module constants; value is validated by
            # mlb_baseball.config._memory_size (or is the literal "off")
            # before it ever reaches here -- psycopg can't parameterize a SET
            # target/value anyway.
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
