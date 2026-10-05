## Purpose

Defines how every external data source is catalogued, ingested into its own raw tables, saved for replay, tracked in the ledger and documented, and the order in which sources are covered.

## ADDED Requirements

### Requirement: Every source has a catalogue page of what it offers versus what is stored
Each source SHALL have a page under `docs/sources/` listing every dataset/endpoint it offers, the years it covers, the raw table that holds each one (or the recorded reason it is not stored), request cost, and rights profile. A reason SHALL be a documented decision, never an unstated omission.

#### Scenario: A dataset is offered but not stored
- **WHEN** a source page lists an offered dataset with no raw table
- **THEN** it names a reason and an owning task or decision, otherwise the docs check fails

#### Scenario: A new raw table lands
- **WHEN** a migration adds a `raw.*` table
- **THEN** the same change updates that source's page and regenerates `docs/RAW_INVENTORY.md`

### Requirement: Overlap between sources is kept, not removed
The system SHALL ingest a dataset into its own source's raw tables even when another source holds the same facts. Raw tables SHALL stay separate per source; reconciliation happens only in `core`.

#### Scenario: Two sources hold the same game's plays
- **WHEN** both the MLB feed and Retrosheet cover a game
- **THEN** each has its own raw rows and neither load modifies the other

### Requirement: Loads are replayable from saved responses
A dataset loader SHALL save each original response (compressed, with checksum) under `downloads/<source>/` before parsing it, SHALL record the artifact path and checksum in `meta.ingestion_item`, and SHALL be able to rebuild its raw tables from those artifacts with no network access.

#### Scenario: Rebuild without the network
- **WHEN** the replay command runs with the network disabled
- **THEN** the raw tables are rebuilt from verified artifacts, and a missing or checksum-mismatched artifact fails the run instead of loading partial data

#### Scenario: A response is a 404
- **WHEN** the source returns 404 for an item
- **THEN** the ledger records it as `unavailable` with the HTTP status, and it is not retried as a failure

### Requirement: The ledger must account for every item
For each ledgered dataset, every expected item SHALL be in a terminal state (`loaded`, `unavailable`, or `failed` with an error). An item with no ledger row SHALL be reported by `mlb doctor` as a gap.

#### Scenario: Interrupted run
- **WHEN** a run is stopped halfway
- **THEN** finished items stay recorded, unfinished ones are retried on the next run, and no finished item is downloaded again

### Requirement: Loads are idempotent and resumable
Re-running a dataset load SHALL NOT duplicate or lose rows. A run SHALL resume from the ledger and SHALL replace only the scopes it reloaded.

#### Scenario: Same load twice
- **WHEN** a loader runs twice on the same inputs
- **THEN** the raw tables are identical after both runs

### Requirement: Rights are checked before ingest
Each source SHALL have a row in `docs/SOURCE_RIGHTS.md` and a data profile before its first ingest. Sources whose terms are unverified (for example Seamheads, KBO, NPB) SHALL NOT be ingested until the review is recorded. Paid providers SHALL NOT be used.

#### Scenario: Source without a rights row
- **WHEN** a connector is added for a source with no rights row
- **THEN** the ingest guard blocks it

### Requirement: Request volume is bounded and declared
Each phase SHALL declare its expected request count, concurrency, and per-second rate before it runs in production, and the loader SHALL honour them with retry and backoff. A phase SHALL NOT start in production without owner approval logged in `pipeline-recovery/results.md`.

#### Scenario: Rate limit response
- **WHEN** the source answers with a throttling or server error
- **THEN** the loader backs off and retries within the declared limits, and records `failed` only after retries are exhausted

### Requirement: Pro data is covered before minor-league and college data
Phases SHALL run in this order: catalogue and rights; cheap MLB endpoints; the per-game MLB feed; re-saved analytics; completeness of the other pro sources; then minor leagues, independent and college data; then sources needing a rights review.

#### Scenario: Minor-league work proposed early
- **WHEN** a task for minor-league or college data is started before the pro phases are complete
- **THEN** it is deferred unless the owner records an exception

### Requirement: A new person can bootstrap everything
`docs/BOOTSTRAP_RUNBOOK.md` SHALL list, in order, the commands that create the database and land every dataset covered by this change, with expected duration, disk use, and request counts per stage.

#### Scenario: Fresh server
- **WHEN** someone follows the runbook on an empty database
- **THEN** every dataset covered here is landed, `mlb doctor` reports its coverage, and `mlb inventory --markdown` matches the catalogue
