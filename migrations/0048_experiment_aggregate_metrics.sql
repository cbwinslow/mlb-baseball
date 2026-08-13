-- Aggregate experiment scores belong on the immutable experiment identity;
-- individual fold scores remain in meta.experiment_fold.

ALTER TABLE meta.experiment
    ADD COLUMN metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb;
