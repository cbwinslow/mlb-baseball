-- Latest result of `mlb schema-watch` per dataset (openspec/changes/source-inventory, task 2.4).
-- One row per (source, dataset), replaced on each run; history is in the nightly log.
-- status: new | unchanged | drift | unchecked. added/removed/changed hold field -> type maps.

CREATE TABLE IF NOT EXISTS meta.schema_finding (
    source text NOT NULL,
    dataset text NOT NULL,
    status text NOT NULL CHECK (status IN ('new', 'unchanged', 'drift', 'unchecked')),
    added jsonb NOT NULL DEFAULT '{}',
    removed jsonb NOT NULL DEFAULT '{}',
    changed jsonb NOT NULL DEFAULT '{}',
    error text NOT NULL DEFAULT '',
    checked_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, dataset)
);
COMMENT ON TABLE meta.schema_finding IS
    'Latest `mlb schema-watch` result per source dataset. drift = fields or files added, removed or retyped since the saved snapshot; unchecked = the source could not be reached (not "unchanged").';
