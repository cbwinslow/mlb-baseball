# source-refresh Specification

## Purpose
Detect that a data publisher changed a file we already downloaded, reload a source from fresh
downloads on request, and report load results unambiguously.

## Requirements

### Requirement: Source check detects upstream changes without downloading

`mlb source-check` SHALL read each download manifest (`downloads/<source>/manifest.json`),
issue one HEAD request per recorded archive URL, and report per source how many archives are
changed, unchanged, unknown, or gone. It SHALL NOT download an archive, write to `downloads/`,
or connect to the database unless `--hash` is given, and then only to a temporary file.

An archive is **changed** when the publisher's `Last-Modified` is later than the recorded
`downloaded_at`, or `Content-Length` differs from the recorded `bytes`. It is **unchanged**
when both are present and agree. It is **unknown** when the response gives neither. It is
**gone** on a 404.

#### Scenario: The publisher republished an archive after we downloaded it

- **WHEN** an archive's `Last-Modified` is later than its recorded `downloaded_at`
- **THEN** the report lists the source as changed with the archive name
- **AND** the report prints the command `mlb ingest <source> --refresh`
- **AND** the process exits non-zero

#### Scenario: Nothing changed

- **WHEN** every archive's headers agree with its manifest entry
- **THEN** the report says no source changed and the process exits zero
- **AND** no file under `downloads/` was created, modified or deleted

#### Scenario: A source has no manifest entries

- **WHEN** a source's manifest is missing or empty
- **THEN** the report lists it as "no download record", not as unchanged

#### Scenario: Full-hash confirmation

- **WHEN** `--hash` is given
- **THEN** each archive is downloaded to a temporary file, its SHA-256 compared with the
  manifest, and the temporary file removed
- **AND** an archive with equal SHA-256 is reported unchanged even if its headers differed

#### Scenario: The publisher cannot be reached

- **WHEN** a request fails after the usual retries
- **THEN** that archive is reported unknown with the error
- **AND** the process exits with a distinct non-zero code from the "changed" exit code

### Requirement: Refresh reloads a source from fresh downloads and keeps the old ones

`mlb ingest <source> --refresh` (bootstrap mode only) SHALL move the source's cached archives
and manifest to `downloads/<source>/_superseded/<UTC timestamp>/` without deleting them, then
run the connector's bootstrap so every archive is fetched and loaded again, including archives
previously marked loaded. It SHALL refuse `--refresh` outside bootstrap mode.

#### Scenario: Refresh a source whose archives changed

- **WHEN** `mlb ingest retrosheet_gamelog --refresh` runs
- **THEN** the previous files and manifest exist under `_superseded/<timestamp>/`
- **AND** the connector downloads and loads every archive again

#### Scenario: Refresh with update mode

- **WHEN** `--refresh` is combined with `--mode update`
- **THEN** the command exits with an error and nothing is moved

### Requirement: Ingestion output states rows loaded and table totals

After a connector run, `mlb ingest` SHALL print, for each table the run reported, the rows
loaded in this run and the table's current total row count. A total that cannot be counted
within 30 seconds SHALL be printed as "not counted", never as a guess.

#### Scenario: A scoped reload skips part of the table

- **WHEN** a run loads fewer rows than the table already holds because some scopes were not
  reloaded
- **THEN** the output shows both numbers, for example `raw.retrosheet_box_game: 17418 loaded,
  18467 in table`

#### Scenario: A count takes too long

- **WHEN** counting a table exceeds 30 seconds
- **THEN** the output shows the loaded rows and "total not counted" for that table
- **AND** the ingestion result is unaffected
