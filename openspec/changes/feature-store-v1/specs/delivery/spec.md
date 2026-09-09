## MODIFIED Requirements

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
**availability timestamp is at or before `t`** (the baseball event had
occurred) **and whose ingest timestamp is at or before `t`** (the warehouse
had already received it). A feature snapshot that a later data delivery would
have changed SHALL NOT be used for a decision time before that delivery. A
missing snapshot SHALL be returned as missing, never filled from a later
snapshot.

The packaged feature build SHALL be reproducible by an installing analyst
**without a PostgreSQL server** — it SHALL run over the published Parquet
(e.g. via DuckDB). The retrieval contract SHALL be exercised by at least one
released notebook that uses only the delivery surface.

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

#### Scenario: A late data delivery does not leak backward

- **WHEN** a source record for an event before decision time `t` is ingested only *after* `t`, and features are requested as of `t`
- **THEN** the returned feature row is computed as if that record were still absent
- **AND** a rebuild after the ingest changes the feature row only for decision times at or after the ingest

#### Scenario: The feature build runs without PostgreSQL

- **WHEN** an analyst runs the packaged feature build against the published Parquet with no database configured
- **THEN** it produces the feature snapshot tables
- **AND** the result matches the project-published feature Parquet within the documented tolerance

### Requirement: The public distribution includes one reference baseline model

The public distribution SHALL include exactly one reference baseline
prediction model (Elo with a home-field and probable-starter adjustment),
its source code, and a model card. The model card SHALL report the model's
calibration, log loss, and Brier score measured on a strictly chronological
hold-out (never a random split), and SHALL state the model's known
limitations.

The model card's numbers SHALL be reproducible by an installing analyst using
the walk-forward backtest harness the distribution ships and the released
feature store — running the harness on the same hold-out SHALL reproduce the
card's calibration, log loss, and Brier score within a documented tolerance.

The reference baseline exists as the worked example every later model is
measured against. (`openspec/project.md`'s phased ladder sequences when it
ships.)

#### Scenario: The baseline model ships with an honest model card

- **WHEN** the public distribution is released
- **THEN** it contains the baseline model's code and a model card
- **AND** the model card reports calibration, log loss, and Brier score from a chronological hold-out and lists the model's limitations

#### Scenario: An analyst reproduces the model card

- **WHEN** an analyst runs the shipped harness on the shipped feature store for the model card's stated hold-out
- **THEN** the calibration, log loss, and Brier score match the model card within the documented tolerance
