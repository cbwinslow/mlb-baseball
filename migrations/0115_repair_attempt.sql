-- One row per `mlb repair --apply` attempt (openspec/changes/source-inventory, task 3.3).
-- Drives the nightly cap (one attempt per table per night) and the suspension rule
-- (three failures in a row since the last reset). outcome: ok | failed | reset.

CREATE TABLE IF NOT EXISTS meta.repair_attempt (
    id bigserial PRIMARY KEY,
    table_name text NOT NULL,
    attempted_at timestamptz NOT NULL DEFAULT now(),
    outcome text NOT NULL CHECK (outcome IN ('ok', 'failed', 'reset')),
    detail text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS repair_attempt_table_idx
    ON meta.repair_attempt (table_name, attempted_at DESC);
COMMENT ON TABLE meta.repair_attempt IS
    'Attempts by `mlb repair --apply`; a reset row ends a suspension after three failures.';
