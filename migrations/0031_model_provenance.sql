-- Immutable model/artifact and execution identity.  Number 0031 deliberately
-- leaves 0029/0030 available while the two existing Claude 0029 worktrees are
-- reconciled (PROJECT_REVIEW.md, Stage 0).

CREATE TABLE meta.model (
    model_id text PRIMARY KEY,
    name text NOT NULL,
    target text NOT NULL,
    model_version text NOT NULL,
    artifact_uri text,
    artifact_sha256 text,
    git_sha text,
    feature_set_version text NOT NULL,
    train_start date,
    train_end date,
    parameters_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL CHECK (status IN ('candidate', 'champion', 'retired', 'baseline')),
    CHECK ((artifact_uri IS NULL) = (artifact_sha256 IS NULL)),
    UNIQUE (artifact_sha256)
);

CREATE UNIQUE INDEX model_one_champion_per_name
    ON meta.model (name) WHERE status = 'champion';

CREATE TABLE meta.model_run (
    run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id text REFERENCES meta.model(model_id),
    run_type text NOT NULL CHECK (run_type IN ('train', 'predict', 'evaluate')),
    data_cutoff timestamptz,
    source_snapshot text,
    feature_snapshot_id text,
    prediction_cutoff text,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    error text
);

ALTER TABLE gold.prediction
    ADD COLUMN model_id text REFERENCES meta.model(model_id),
    ADD COLUMN model_run_id bigint REFERENCES meta.model_run(run_id),
    ADD COLUMN data_cutoff timestamptz,
    ADD COLUMN prediction_cutoff text,
    ADD COLUMN feature_snapshot_id text;

CREATE INDEX prediction_model_id_idx ON gold.prediction (model_id);
CREATE INDEX prediction_model_run_id_idx ON gold.prediction (model_run_id);
