-- Forward-stepwise feature selection with nested chronological validation.

CREATE TABLE meta.feature_selection_stepwise (
    selection_id text PRIMARY KEY,
    snapshot_id text NOT NULL REFERENCES meta.experiment_snapshot(snapshot_id),
    target text NOT NULL REFERENCES meta.experiment_target(name),
    fold_plan_json jsonb NOT NULL,
    method_config_json jsonb NOT NULL,
    status text NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    error text,
    result_json jsonb,
    artifact_uri text,
    artifact_sha256 text,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);
