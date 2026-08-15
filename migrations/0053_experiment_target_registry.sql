-- Target registry for experiment lab (classification and regression).

CREATE TABLE meta.experiment_target (
    name text PRIMARY KEY,
    task_type text NOT NULL CHECK (task_type IN ('classification', 'regression')),
    description text NOT NULL
);

INSERT INTO meta.experiment_target (name, task_type, description) VALUES
    ('home_win', 'classification', 'Game outcome (home win vs. loss)'),
    ('run_differential', 'regression', 'Final score margin (home score minus away score)');

ALTER TABLE meta.experiment_snapshot
    DROP CONSTRAINT experiment_snapshot_target_check;

ALTER TABLE meta.experiment_snapshot
    ADD CONSTRAINT experiment_snapshot_target_fkey
    FOREIGN KEY (target) REFERENCES meta.experiment_target(name);

ALTER TABLE meta.experiment
    DROP CONSTRAINT experiment_target_check;

ALTER TABLE meta.experiment
    ADD CONSTRAINT experiment_target_fkey
    FOREIGN KEY (target) REFERENCES meta.experiment_target(name);

ALTER TABLE meta.experiment_snapshot
    DROP CONSTRAINT experiment_snapshot_row_sha256_key;

ALTER TABLE meta.experiment_snapshot
    ADD CONSTRAINT experiment_snapshot_row_sha256_target_key
    UNIQUE (row_sha256, target);
