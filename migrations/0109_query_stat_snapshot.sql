-- Nightly copy of pg_stat_statements so slow-statement history survives the
-- extension's small in-memory window (pg_stat_statements.max) and server
-- restarts. Counters are cumulative: a statement's cost over a period is the
-- difference between two snapshots (clamped at zero if the stats were reset).
-- Written by `mlb nightly` (mlb_baseball/nightly.py), which keeps 180 days.

CREATE TABLE meta.query_stat_snapshot (
    snapshot_at timestamptz NOT NULL,
    queryid bigint NOT NULL,
    calls bigint NOT NULL,
    total_exec_time_ms double precision NOT NULL,
    rows bigint NOT NULL,
    shared_blks_hit bigint NOT NULL,
    shared_blks_read bigint NOT NULL,
    temp_blks_written bigint NOT NULL,
    wal_bytes numeric NOT NULL,
    query text NOT NULL,
    PRIMARY KEY (snapshot_at, queryid)
);
