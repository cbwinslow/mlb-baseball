-- Durable identities for the in-place game-feature build and game-grain
-- evaluations.  A snapshot records a reproducible *fingerprint*, not a copy:
-- gold.game_feature is currently rebuilt in place, so it cannot recover old
-- feature rows by itself.  A later immutable feature store can retain the same
-- identifier and add physical storage without rewriting model provenance.

CREATE TABLE meta.feature_snapshot (
    feature_snapshot_id text PRIMARY KEY,
    feature_set_version text NOT NULL,
    data_cutoff timestamptz,
    row_count bigint NOT NULL,
    latest_game_date date,
    built_at timestamptz,
    identity_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE meta.model_evaluation (
    evaluation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id bigint NOT NULL REFERENCES meta.model_run(run_id),
    model_versions jsonb NOT NULL,
    season integer NOT NULL,
    prediction_cutoff text NOT NULL,
    common_games integer NOT NULL,
    coverage_json jsonb NOT NULL,
    metrics_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id)
);

CREATE INDEX model_evaluation_season_cutoff_idx
    ON meta.model_evaluation (season, prediction_cutoff, created_at DESC);
