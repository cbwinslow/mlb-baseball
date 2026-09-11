# Delivery Surface Specification

## Purpose

Defines how the research `gold` stat backbone leaves this repository: a
deterministic Parquet export, a versioned public dataset, an in-browser SQL
query surface, and a Python loader package. The contract is what an outside
analyst relies on — file layout, schema stability, versioning, and rights —
not how any of it is implemented.

## Requirements

### Requirement: Parquet export of the research backbone

The system SHALL export a fixed set of research `gold` tables to columnar
Parquet, one file per table, plus a machine-readable manifest describing
every file (table name, row count, column names and types, source table,
build timestamp, schema version).

The export SHALL be **deterministic**: the same database state produces
byte-comparable Parquet content and an identical manifest (ordering fixed,
no embedded run-specific values beyond a single recorded build timestamp).

The export SHALL be **idempotent**: re-running it over the same database
state replaces the output in place without duplicating or corrupting it.

The exported table set SHALL be exactly: `batting_game`, `pitching_game`,
`batting_season`, `pitching_season`, `batting_team`, `pitching_team`,
`batting_career`, `pitching_career`, `player_season`, `team_season`.

#### Scenario: Export produces one Parquet per table plus a manifest

- **WHEN** the export runs against a database with all ten backbone tables populated
- **THEN** it writes exactly ten Parquet files (one per table) and one manifest file
- **AND** the manifest lists every file with its row count, column schema, and source table

#### Scenario: Re-running the export is idempotent

- **WHEN** the export is run twice against the same database state
- **THEN** the second run leaves the same set of files with the same row counts
- **AND** no file is duplicated or left partially written

#### Scenario: A table missing from the database is reported, not silently skipped

- **WHEN** the export runs and one backbone table has zero rows or does not exist
- **THEN** the export fails with a non-zero exit (or records the gap explicitly in the manifest and its log)
- **AND** the failure names the missing table

### Requirement: Source-rights gate at export time

The export SHALL check each table against the project's source-profile
rules before writing it. A table that is not eligible for public
distribution SHALL be excluded from the export, with the exclusion and its
reason recorded in the log and the manifest.

The export SHALL NOT publish a table whose eligibility is unknown; unknown
is treated as not eligible.

#### Scenario: An ineligible table is excluded with a recorded reason

- **WHEN** the export encounters a table whose source profile disallows public distribution
- **THEN** that table is not written to Parquet
- **AND** the manifest and log record the table name and the reason it was excluded

### Requirement: Versioned publication to a public dataset host

The Parquet files and manifest SHALL be publishable to a public dataset
host (Hugging Face Datasets) as a named dataset, versioned by the release
tag that produced them. Each published version SHALL be retrievable by that
tag.

The publish step SHALL take its write credential from the runtime
environment (`HF_TOKEN`). The credential SHALL NOT appear in the repository,
in committed files, in logs, or in the dataset itself.

The published dataset SHALL include a dataset card stating: the source
(Retrosheet-derived, event-computed), the coverage (seasons, regular
season only), the licence (AGPL-consistent / CC-appropriate), the schema
version, and a link back to this repository and to `docs/RESEARCH.md`'s
honest-limitations content.

#### Scenario: A tagged release publishes a retrievable dataset version

- **WHEN** the publish step runs for release tag `vX.Y.Z` with a valid `HF_TOKEN` in the environment
- **THEN** the dataset host has a version labelled `vX.Y.Z` containing the ten Parquet files, the manifest, and the dataset card
- **AND** that version can be downloaded by specifying the tag

#### Scenario: The write token never leaks

- **WHEN** the publish step runs
- **THEN** `HF_TOKEN` does not appear in any committed file, any log line, or any published artifact

### Requirement: In-browser SQL query surface

The project SHALL publish a static web page that lets a visitor run SQL
against the published Parquet **entirely in their browser**, with no
server-side query execution and no backend the project pays to host.

The page SHALL load the current published dataset version, expose the ten
backbone tables as queryable relations, run a visitor-entered SQL query,
and display the result as a table. A query error SHALL be shown to the
visitor as a readable message, not a blank result or a console-only error.

#### Scenario: A visitor runs a query and sees results

- **WHEN** a visitor opens the query page and submits `SELECT * FROM batting_season WHERE season = 2023 LIMIT 5`
- **THEN** the page fetches the needed Parquet, runs the query client-side, and shows five rows
- **AND** no request is made to a project-operated query backend

#### Scenario: A bad query shows a readable error

- **WHEN** a visitor submits SQL that references a non-existent column
- **THEN** the page shows the database's error message in the UI

### Requirement: `mlb-research` Python loader package

The project SHALL provide a Python package, importable as `mlb_research`,
that resolves a released dataset version, downloads and caches its Parquet
locally, and returns a table as a DataFrame via a documented `load()`
call.

`load(table, ...)` SHALL accept a table name from the backbone set and
optional row filters (at minimum `season`), return a DataFrame with the
table's documented schema, and raise a clear error for an unknown table
name or an unreachable dataset version.

The package SHALL cache downloaded files so a repeat `load()` of the same
version does no network I/O, and SHALL let the caller pin a specific
released version.

#### Scenario: load returns a DataFrame for a known table

- **WHEN** a user calls `mlb_research.load("pitching_season", season=2023)`
- **THEN** the package downloads (or reuses a cached copy of) the current version's Parquet
- **AND** returns a DataFrame containing only 2023 rows with the documented `pitching_season` columns

#### Scenario: Unknown table name fails clearly

- **WHEN** a user calls `mlb_research.load("not_a_table")`
- **THEN** the call raises an error that names the bad table and lists the valid ones

#### Scenario: Repeat load is offline

- **WHEN** `load()` is called twice for the same table and version
- **THEN** the second call performs no network request

### Requirement: A runnable example notebook

The project SHALL include **at least five** notebooks, each answering a distinct
concrete analyst question using **only the released delivery surface** (the
`mlb-research` package or the published Parquet), never a live database
connection. Each notebook SHALL run end to end from a clean environment with the
package installed, and SHALL recompute any rate from summed numerators and
denominators rather than averaging already-computed rates.

#### Scenario: The example notebook runs against released data only

- **WHEN** any notebook under `notebooks/` is executed in a clean environment
  with `mlb-research` installed
- **THEN** it completes without error
- **AND** it makes no connection to a Postgres database and imports no
  database-layer package

#### Scenario: The notebook set covers at least five distinct questions

- **WHEN** the `notebooks/` directory is listed
- **THEN** there are at least five runnable notebooks
- **AND** each answers a different analyst question, not five variations of one

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

### Requirement: Published documentation site

The project SHALL publish a static documentation website that an outside
analyst can read **without cloning the repository or running anything**,
covering at minimum:

- a **data dictionary** of every table in the published backbone set — its
  grain, its columns and their types, its source, and its null policy;
- a **grain-ladder** explanation with a diagram, stating that season, team, and
  career figures are recomputed from the finer grain's numerators and
  denominators and never averaged from already-computed rates;
- **formula citations** — for every metric the project publishes, its formula
  and the published source it is cited to;
- an **honest-limitations** page — coverage boundaries, regular-season-only
  scope, known tie-out tolerances, and the "a missing measurement is not zero"
  rule.

The site SHALL be deployed at no hosting cost through the same static
GitHub Pages workflow that publishes the in-browser query page — not a second
workflow or a paid service. The in-browser query page SHALL remain reachable at
its existing path after the documentation site is published.

The data-dictionary content SHALL have a single source of truth in the
repository: the published page SHALL be generated from that source, not
maintained as a second hand-edited copy that can drift.

#### Scenario: A visitor reads the documented backbone without cloning the repo

- **WHEN** a visitor opens the published documentation site
- **THEN** they can read the data dictionary, the grain-ladder diagram, the
  cited formulas, and the honest-limitations page as rendered web pages
- **AND** no step requires cloning the repository, installing a package, or
  running a build

#### Scenario: The query page still works after the docs site ships

- **WHEN** the documentation site is deployed
- **THEN** the in-browser SQL query page is still reachable at its previous path
- **AND** it still runs queries entirely client-side against the published
  dataset

#### Scenario: The data dictionary cannot silently drift

- **WHEN** a column is added, renamed, or removed from a published backbone table
  and the repository's canonical data-dictionary source is updated
- **THEN** rebuilding the site reflects that change on the published
  data-dictionary page with no separate edit to the site
