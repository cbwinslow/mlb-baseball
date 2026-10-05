-- Run monitor (openspec/changes/odds-bulk-history, section 2; ADR-295).
-- Gives every long job a progress record, every operation a timing row, and every
-- item failure a history, using database functions, a trigger, a procedure and
-- views so ALL writers (Python, SQL, psql) are captured the same way.
--
--   meta.ingestion_run   + items_planned / items_done / requests / last_progress_at
--   meta.ingestion_item  + duration_ms
--   meta.ingestion_item_history  append-only: failures and status changes (trigger)
--   meta.op_span         one row per timed operation (mlb_baseball.opsmon)
--   meta.run_progress()  throttled progress write
--   meta.record_op()     insert one timed operation
--   meta.stuck_runs()    running jobs that reported progress once but went quiet
--   meta.run_health      rate, ETA and silence per run
--   meta.op_summary      per-operation counts, failures and p50/p95 over 7 days
--   meta.prune_ops()     retention (procedure, called by `mlb nightly`)

ALTER TABLE meta.ingestion_run
    ADD COLUMN IF NOT EXISTS items_planned bigint,
    ADD COLUMN IF NOT EXISTS items_done bigint,
    ADD COLUMN IF NOT EXISTS requests bigint,
    ADD COLUMN IF NOT EXISTS last_progress_at timestamptz;

ALTER TABLE meta.ingestion_item
    ADD COLUMN IF NOT EXISTS duration_ms integer;

CREATE TABLE IF NOT EXISTS meta.ingestion_item_history (
    id bigserial PRIMARY KEY,
    source text NOT NULL,
    dataset text NOT NULL,
    item_key text NOT NULL,
    status text NOT NULL,
    attempts integer,
    error text,
    http_status integer,
    rows integer,
    run_id bigint,
    duration_ms integer,
    recorded_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ingestion_item_history_item_idx
    ON meta.ingestion_item_history (source, dataset, item_key);
CREATE INDEX IF NOT EXISTS ingestion_item_history_recorded_idx
    ON meta.ingestion_item_history (recorded_at);

CREATE TABLE IF NOT EXISTS meta.op_span (
    id bigserial PRIMARY KEY,
    run_id bigint REFERENCES meta.ingestion_run (id) ON DELETE SET NULL,
    op text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    duration_ms bigint NOT NULL,
    status text NOT NULL CHECK (status IN ('ok', 'failed')),
    rows bigint,
    requests integer,
    attrs jsonb NOT NULL DEFAULT '{}'::jsonb,
    error text
);
CREATE INDEX IF NOT EXISTS op_span_op_started_idx ON meta.op_span (op, started_at DESC);
CREATE INDEX IF NOT EXISTS op_span_run_idx ON meta.op_span (run_id);

-- Trigger: keep the history of every failure and every status change of an item,
-- whoever writes it. A first-time successful load is not recorded (it would only
-- double the table); a failure, or any later change of status or error, is.
CREATE OR REPLACE FUNCTION meta.record_item_history() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (TG_OP = 'INSERT' AND NEW.status = 'failed')
       OR (TG_OP = 'UPDATE' AND (NEW.status IS DISTINCT FROM OLD.status
                                 OR NEW.error IS DISTINCT FROM OLD.error)) THEN
        INSERT INTO meta.ingestion_item_history
            (source, dataset, item_key, status, attempts, error, http_status,
             rows, run_id, duration_ms)
        VALUES
            (NEW.source, NEW.dataset, NEW.item_key, NEW.status, NEW.attempts, NEW.error,
             NEW.http_status, NEW.rows, NEW.run_id, NEW.duration_ms);
    END IF;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS ingestion_item_history_trg ON meta.ingestion_item;
CREATE TRIGGER ingestion_item_history_trg
    AFTER INSERT OR UPDATE ON meta.ingestion_item
    FOR EACH ROW EXECUTE FUNCTION meta.record_item_history();

-- Function: write progress at most once per p_min_interval; returns whether it wrote.
CREATE OR REPLACE FUNCTION meta.run_progress(
    p_run_id bigint,
    p_done bigint,
    p_planned bigint,
    p_requests bigint DEFAULT NULL,
    p_min_interval interval DEFAULT interval '30 seconds'
) RETURNS boolean
LANGUAGE plpgsql AS $$
DECLARE
    v_rows integer;
BEGIN
    UPDATE meta.ingestion_run
       SET items_done = p_done,
           items_planned = COALESCE(p_planned, items_planned),
           requests = COALESCE(p_requests, requests),
           last_progress_at = now()
     WHERE id = p_run_id
       AND (last_progress_at IS NULL OR last_progress_at <= now() - p_min_interval);
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows > 0;
END;
$$;

CREATE OR REPLACE FUNCTION meta.record_op(
    p_op text,
    p_started_at timestamptz,
    p_duration_ms bigint,
    p_status text,
    p_rows bigint DEFAULT NULL,
    p_requests integer DEFAULT NULL,
    p_attrs jsonb DEFAULT '{}'::jsonb,
    p_error text DEFAULT NULL,
    p_run_id bigint DEFAULT NULL
) RETURNS bigint
LANGUAGE sql AS $$
    INSERT INTO meta.op_span
        (run_id, op, started_at, duration_ms, status, rows, requests, attrs, error)
    VALUES
        (p_run_id, p_op, p_started_at, p_duration_ms, p_status, p_rows, p_requests,
         COALESCE(p_attrs, '{}'::jsonb), p_error)
    RETURNING id;
$$;

-- View: how fast each run is going and how long until it finishes.
CREATE OR REPLACE VIEW meta.run_health AS
SELECT r.id AS run_id,
       r.source,
       r.mode,
       r.status,
       r.started_at,
       r.items_planned,
       r.items_done,
       r.requests,
       r.last_progress_at,
       EXTRACT(EPOCH FROM (COALESCE(r.finished_at, now()) - r.started_at)) AS elapsed_seconds,
       EXTRACT(EPOCH FROM (now() - COALESCE(r.last_progress_at, r.started_at)))
           AS seconds_since_progress,
       r.items_done::numeric
           / NULLIF(EXTRACT(EPOCH FROM (COALESCE(r.finished_at, now()) - r.started_at)), 0)
           AS items_per_second,
       (r.items_planned - r.items_done)
           / NULLIF(r.items_done::numeric
                    / NULLIF(EXTRACT(EPOCH FROM (COALESCE(r.finished_at, now()) - r.started_at)),
                             0), 0) AS eta_seconds
FROM meta.ingestion_run AS r;

-- Function: running jobs that opted in to progress reporting (items_planned set)
-- and have been silent longer than p_max_gap. Jobs that never report are not judged.
CREATE OR REPLACE FUNCTION meta.stuck_runs(p_max_gap interval DEFAULT interval '15 minutes')
RETURNS TABLE (
    run_id bigint,
    source text,
    mode text,
    started_at timestamptz,
    last_progress_at timestamptz,
    silent_seconds numeric,
    items_done bigint,
    items_planned bigint
)
LANGUAGE sql STABLE AS $$
    SELECT r.id, r.source, r.mode, r.started_at, r.last_progress_at,
           EXTRACT(EPOCH FROM (now() - COALESCE(r.last_progress_at, r.started_at))),
           r.items_done, r.items_planned
    FROM meta.ingestion_run AS r
    WHERE r.status = 'running'
      AND r.items_planned IS NOT NULL
      AND COALESCE(r.last_progress_at, r.started_at) < now() - p_max_gap;
$$;

CREATE OR REPLACE VIEW meta.op_summary AS
SELECT op,
       count(*) AS calls,
       count(*) FILTER (WHERE status = 'failed') AS failures,
       round(avg(duration_ms)) AS avg_ms,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms) AS p50_ms,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms,
       sum(rows) AS total_rows,
       sum(requests) AS total_requests,
       max(started_at) AS last_seen
FROM meta.op_span
WHERE started_at >= now() - interval '7 days'
GROUP BY op;

-- Procedure: retention for the monitor tables.
CREATE OR REPLACE PROCEDURE meta.prune_ops(p_keep interval DEFAULT interval '180 days')
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM meta.op_span WHERE started_at < now() - p_keep;
    DELETE FROM meta.ingestion_item_history WHERE recorded_at < now() - p_keep;
END;
$$;
