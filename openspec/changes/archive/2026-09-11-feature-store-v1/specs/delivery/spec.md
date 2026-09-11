## MODIFIED Requirements

### Requirement: The public distribution is a research platform, not only a data dump

The public `mlb-research` distribution SHALL include, alongside the Parquet
tables and loader, a **point-in-time feature set** and a documented as-of
retrieval contract over it, so an analyst can assemble training data for a
stated decision time without hand-writing the leakage guard.

The retrieval contract SHALL guarantee that, for every requested
`(entity, decision time t)` pair:

- every returned feature value was derived only from records observable at or
  before `t` — the baseball event had occurred and its result was available
  (a per-source availability lag SHALL be documented, not assumed to be zero);
- a feature with no qualifying value at `t` is returned as **missing** — never
  filled from a later value, never forward-filled, never defaulted to zero;
- exactly one output row is returned per requested input row.

Where the feature store is rebuilt **incrementally** (a build that appends to an
earlier one rather than replacing it), retrieval SHALL additionally exclude any
value that a data delivery *after* `t` would have changed — a row's ingest
timestamp gates its visibility. A full rebuild has no such ordering and this
clause does not apply to it.

Published feature files SHALL be **immutable within a release tag**: a value
published under a tag is never edited in place. A corrected or redefined
feature SHALL be published under a new feature version, and the superseded
version SHALL remain retrievable at its original tag.

The distribution SHALL ship the feature build logic, not only its output: an
installing analyst SHALL be able to reproduce the feature set **from their own
build** of the source data, using only code the distribution ships, and the
result SHALL match the project-published feature files within a documented
tolerance. **Retrieval** from a feature set — published or locally built —
SHALL require no database server.

The retrieval contract SHALL be exercised by at least one runnable example that
uses only the delivery surface, and the leakage checks that enforce the
guarantees above SHALL ship with the distribution and be runnable by an analyst
against their own build.

(This requirement names the guarantee, not an implementation. No particular
table shape, storage engine, key layout, or third-party feature-store framework
is mandated — only that the guarantees hold and that the retrieval join is
documented. The public roadmap in `openspec/project.md` sequences when each
part ships.)

#### Scenario: The released product includes a usable feature store

- **WHEN** an analyst installs the public distribution and requests features for a set of games at their scheduled first-pitch times
- **THEN** they receive one feature row per game built only from data available before that game's first pitch
- **AND** the leakage checks that enforce the point-in-time guarantee are present in the distribution and runnable against their own build

#### Scenario: As-of retrieval does not leak the future

- **WHEN** a feature is requested as of a timestamp that falls before a later snapshot for the same entity
- **THEN** the earlier snapshot is returned
- **AND** the later snapshot is not used, even if no earlier snapshot exists (the result is missing)

#### Scenario: An incremental build does not let a late delivery leak backward

- **WHEN** the feature store is built incrementally, a source record for an event before decision time `t` is appended to the store only *after* `t`, and features are requested as of `t`
- **THEN** the returned feature row is computed as if that record were still absent
- **AND** a later incremental build that includes the record changes the returned row only for decision times at or after the record was appended

#### Scenario: Two games on the same day are ordered by time, not by date

- **WHEN** features are requested as of the first pitch of the second game of a same-day doubleheader
- **THEN** the returned row reflects no result from the first game of that doubleheader
- **AND** features requested as of the following day's first pitch do reflect it

#### Scenario: An analyst reproduces the feature set from their own build

- **WHEN** an analyst runs the distribution's documented bootstrap-and-build path against their own environment
- **THEN** the feature set is produced locally by shipped code
- **AND** it matches the project-published feature files within the documented tolerance

#### Scenario: Retrieval needs no database server

- **WHEN** an analyst retrieves features from a feature set with no database server configured or running
- **THEN** the retrieval succeeds and returns the point-in-time-correct rows

### Requirement: The public distribution includes one reference baseline model

The public distribution SHALL include exactly one reference baseline
prediction model (Elo with a home-field and probable-starter adjustment),
its source code, and a model card. The model card SHALL report the model's
calibration, log loss, and Brier score measured on a strictly chronological
hold-out (never a random split), and SHALL state the model's known
limitations.

Every input the reference baseline consumes SHALL be reproducible from the
analyst's own build. The baseline SHALL NOT depend on a project-operated
service, a private or non-shipped data feed, a shipped trained artifact, or any
relation whose build logic the distribution withholds.

The model card's numbers SHALL be reproducible by an installing analyst running
the walk-forward backtest harness the distribution ships against their own build
of the card's stated hold-out — reproducing the card's calibration, log loss,
and Brier score within a documented tolerance.

The reference baseline exists as the worked example every later model is
measured against. (`openspec/project.md`'s phased ladder sequences when it
ships.)

#### Scenario: The baseline model ships with an honest model card

- **WHEN** the public distribution is released
- **THEN** it contains the baseline model's code and a model card
- **AND** the model card reports calibration, log loss, and Brier score from a chronological hold-out and lists the model's limitations

#### Scenario: The baseline consumes only inputs the analyst can rebuild

- **WHEN** the reference baseline is run in an environment produced solely by the distribution's own bootstrap-and-build path
- **THEN** every feature it reads is present
- **AND** it produces predictions without any project-operated service, non-shipped feed, or pre-trained artifact

#### Scenario: An analyst reproduces the model card

- **WHEN** an analyst runs the shipped harness against their own build for the model card's stated hold-out
- **THEN** the calibration, log loss, and Brier score match the model card within the documented tolerance
