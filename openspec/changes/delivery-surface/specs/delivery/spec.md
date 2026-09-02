## Purpose

Defines how the research `gold` stat backbone leaves this repository: a
deterministic Parquet export, a versioned public dataset, an in-browser SQL
query surface, and a Python loader package. The contract is what an outside
analyst relies on — file layout, schema stability, versioning, and rights —
not how any of it is implemented.

## ADDED Requirements

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

The project SHALL include at least one notebook that answers a concrete
analyst question using **only the released delivery surface** (the
`mlb-research` package or the published Parquet), never a live database
connection. The notebook SHALL run end to end from a clean environment
with the package installed.

#### Scenario: The example notebook runs against released data only

- **WHEN** the example notebook is executed in a clean environment with `mlb-research` installed
- **THEN** it completes without error
- **AND** it makes no connection to a Postgres database
