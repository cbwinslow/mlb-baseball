## ADDED Requirements

### Requirement: The public distribution is a research platform, not only a data dump

The public `mlb-research` distribution SHALL include, alongside the Parquet
tables and loader, a **point-in-time feature store**: append-only feature
snapshot tables keyed by entity and an availability timestamp, an as-of
retrieval contract that returns each feature as it stood before a given
decision time, a machine-readable feature registry (name, entity, version,
inputs, availability rule, null policy), and a leakage-test battery that
ships and runs against it.

The feature store's retrieval contract SHALL guarantee that a feature value
returned for decision time `t` was derived only from records whose
availability timestamp is at or before `t`. A missing snapshot SHALL be
returned as missing, never filled from a later snapshot.

(The public roadmap in `openspec/project.md` sequences when the feature
store ships — see its phased ladder. This requirement defines what the
public distribution is, not when each part lands.)

#### Scenario: The released product includes a usable feature store

- **WHEN** an analyst installs the public distribution and requests features for a set of games at their scheduled first-pitch times
- **THEN** they receive one feature row per game built only from data available before that game's first pitch
- **AND** the feature registry and the leakage-test battery are present in the distribution

#### Scenario: As-of retrieval does not leak the future

- **WHEN** a feature is requested as of a timestamp that falls before a later snapshot for the same entity
- **THEN** the earlier snapshot is returned
- **AND** the later snapshot is not used, even if no earlier snapshot exists (the result is missing)

### Requirement: The public distribution includes one reference baseline model

The public distribution SHALL include exactly one reference baseline
prediction model (Elo with a home-field and probable-starter adjustment),
its source code, and a model card. The model card SHALL report the model's
calibration, log loss, and Brier score measured on a strictly chronological
hold-out (never a random split), and SHALL state the model's known
limitations.

The reference baseline exists as the worked example every later model is
measured against. (`openspec/project.md`'s phased ladder sequences when it
ships.)

#### Scenario: The baseline model ships with an honest model card

- **WHEN** the public distribution is released
- **THEN** it contains the baseline model's code and a model card
- **AND** the model card reports calibration, log loss, and Brier score from a chronological hold-out and lists the model's limitations

### Requirement: Internal Engine artifacts are never published

The public distribution SHALL NOT contain trained model weights or
artifacts, tuned hyperparameter or configuration files, or backtest results
for any model other than the reference baseline. Eligibility is treated the
same way as source rights: an artifact whose classification is unknown is
excluded.

#### Scenario: A tuned model artifact is excluded from the release

- **WHEN** the export/publish step runs and a trained model artifact or a tuned-hyperparameter file is present in the working tree
- **THEN** it is not included in the published distribution
- **AND** the exclusion is recorded in the publish log

#### Scenario: Only the reference baseline's evaluation is published

- **WHEN** the public distribution is released
- **THEN** it contains the reference baseline's model card and evaluation numbers
- **AND** it contains no backtest results, calibration numbers, or model cards for any other model
