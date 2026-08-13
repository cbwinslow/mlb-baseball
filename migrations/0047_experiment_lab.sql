-- Immutable, narrow game-win experiment inputs and results.  The live
-- gold.game_feature relation is intentionally rebuilt in place, so an
-- experiment must never rely on it remaining unchanged after a run finishes.

CREATE TABLE meta.experiment_snapshot (
    snapshot_id text PRIMARY KEY,
    feature_set_version text NOT NULL,
    target text NOT NULL CHECK (target = 'home_win'),
    source_profile text NOT NULL,
    selection_sql text NOT NULL,
    selection_sha256 text NOT NULL,
    row_sha256 text NOT NULL UNIQUE,
    source_watermark timestamptz,
    row_count bigint NOT NULL CHECK (row_count > 0),
    feature_columns jsonb NOT NULL,
    schema_json jsonb NOT NULL,
    environment_json jsonb NOT NULL,
    git_sha text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE gold.game_feature_snapshot (
    snapshot_id text NOT NULL REFERENCES meta.experiment_snapshot(snapshot_id),
    game_instance_key text NOT NULL,
    mlb_game_pk text NOT NULL,
    feature_cutoff_at timestamptz NOT NULL,
    season integer NOT NULL,
    game_date date NOT NULL,
    game_number integer,
    home_team_id bigint NOT NULL,
    away_team_id bigint NOT NULL,
    home_score integer NOT NULL,
    away_score integer NOT NULL,
    feature_json jsonb NOT NULL,
    home_win boolean NOT NULL,
    PRIMARY KEY (snapshot_id, game_instance_key),
    UNIQUE (snapshot_id, mlb_game_pk)
);

CREATE INDEX game_feature_snapshot_fold_idx
    ON gold.game_feature_snapshot (snapshot_id, season, feature_cutoff_at, game_number, mlb_game_pk);

CREATE TABLE meta.experiment (
    experiment_id text PRIMARY KEY,
    snapshot_id text NOT NULL REFERENCES meta.experiment_snapshot(snapshot_id),
    target text NOT NULL CHECK (target = 'home_win'),
    source_profile text NOT NULL,
    fold_plan_json jsonb NOT NULL,
    model_family text NOT NULL,
    parameters_json jsonb NOT NULL,
    seed integer NOT NULL,
    calibration text NOT NULL CHECK (calibration IN ('none')),
    code_sha text,
    status text NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    error text,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    UNIQUE (snapshot_id, target, source_profile, fold_plan_json, model_family, parameters_json, seed, calibration)
);

CREATE TABLE meta.experiment_fold (
    experiment_id text NOT NULL REFERENCES meta.experiment(experiment_id),
    fold_name text NOT NULL,
    train_through_season integer NOT NULL,
    test_season integer NOT NULL,
    eligible_rows integer NOT NULL,
    train_rows integer NOT NULL,
    test_rows integer NOT NULL,
    metrics_json jsonb NOT NULL,
    prediction_sha256 text NOT NULL,
    artifact_uri text NOT NULL,
    artifact_sha256 text NOT NULL,
    status text NOT NULL CHECK (status IN ('success', 'failed')),
    error text,
    PRIMARY KEY (experiment_id, fold_name)
);

CREATE INDEX experiment_snapshot_idx ON meta.experiment (snapshot_id, started_at DESC);
