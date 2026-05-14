# Raw Data Ingestion Completion Plan

## Objective

Complete the raw data ingestion layer by:
1. Creating raw table SQL scripts for ESPN and Weather sources
2. Creating ingestor classes for FanGraphs, Lahman, ESPN, and Weather sources
3. Fixing the MLB StatsAPI ingestor to write to raw tables instead of core tables
4. Ensuring all ingestors follow a consistent pattern and proper error handling

## Implementation Plan

### Phase 1: Create Missing Raw Table SQL Scripts

#### ESPN Raw Tables
- [ ] Create `sql/70_tables_raw/25_raw_espn.sql` with tables for:
  * ESPN scoreboard data (games, teams, venues, broadcasts)
  * ESPN standings data
  * ESPN team/player info if available from the API
  * Include proper header with source, URL, access date, and attribution
  * Add appropriate indexes for query performance

#### Weather Raw Tables
- [ ] Create `sql/70_tables_raw/26_raw_weather.sql` with tables for:
  * NOAA weather forecast data (periods, temperature, precipitation, etc.)
  * Weather station metadata
  * Include proper header with source, URL, access date, and attribution
  * Add appropriate indexes for query performance

### Phase 2: Fix MLB StatsAPI Ingestor

#### Modify MLBIngestor
- [ ] Update `baseball/sources/mlb/ingestor.py` to write to raw tables (`raw.mlb_*`) instead of `baseball.mlb_schedule`
- [ ] Create separate ingest methods for each raw table:
  * `ingest_schedule()` → `raw.mlb_schedule`
  * `ingest_game_data()` → `raw.mlb_game`, `raw.mlb_team`, etc.
  * `ingest_standings()` → `raw.mlb_standings`
  * `ingest_roster()` → `raw.mlb_roster`
- [ ] Update column mappings to match raw table definitions in `01_raw_mlbstatsapi.sql`
- [ ] Ensure all methods support dry-run mode and batch processing
- [ ] Maintain consistent error handling and logging patterns

### Phase 3: Create Missing Ingestors

#### FanGraphs Ingestor
- [ ] Create `baseball/sources/fangraphs/ingestor.py` with:
  * `FanGraphsIngestor` class following the same pattern as existing ingestors
  * Methods to ingest:
    - Batting statistics (CSV → `raw.fg_batting`)
    - Pitching statistics (CSV → `raw.fg_pitching`)
    - Fielding statistics (CSV → `raw.fg_fielding`)
  * Dry-run support, batch processing, proper error handling
  * Source URL and loaded_at metadata tracking
  * Column mapping from FanGraphs CSV exports to raw table columns

#### Lahman Ingestor
- [ ] Create `baseball/sources/lahman/ingestor.py` with:
  * `LahmanIngestor` class following the same pattern
  * Methods to ingest each Lahman CSV table:
    - People (→ `raw.lahman_people` or equivalent)
    - Batting (→ `raw.lahman_batting`)
    - Pitching (→ `raw.lahman_pitching`)
    - Fielding (→ `raw.lahman_fielding`)
    - And all other tables found in the Lahman database
  * Handle reading from extracted CSV files in Lahman ZIP structure
  * Dry-run support, batch processing, proper error handling

#### ESPN Ingestor
- [ ] Create `baseball/sources/espn/ingestor.py` with:
  * `ESPNIngestor` class following the same pattern
  * Methods to ingest:
    - Scoreboard data (JSON → ESPN raw tables)
    - Standings data (if available separately)
  * Dry-run support, batch processing, proper error handling
  * Source URL and loaded_at metadata tracking
  * Mapping from ESPN JSON response to raw table columns

#### Weather Ingestor
- [ ] Create `baseball/sources/weather/ingestor.py` with:
  * `WeatherIngestor` class following the same pattern
  * Methods to ingest:
    - Forecast data (JSON → weather raw tables)
  * Dry-run support, batch processing, proper error handling
  * Source URL and loaded_at metadata tracking
  * Mapping from NOAA JSON response to raw table columns

### Phase 4: Standardize and Test

#### Ingestor Consistency
- [ ] Verify all ingestors follow the same interface:
  * `__init__(db_connection: Optional[Engine] = None)`
  * Dry-run detection (`self._dry_run = db_connection is None`)
  * Batch processing capabilities
  * Consistent error handling and logging
  * Return `IngestResult` objects with standard fields
- [ ] Consider creating a base `BaseIngestor` class to enforce consistency
- [ ] Update `baseball/sources/registry.py` to include all new ingestors

#### CLI Integration
- [ ] Verify the CLI `ingest` command can handle all source types:
  * `baseball ingest fangraphs --<options>`
  * `baseball ingest lahman --<options>`
  * `baseball ingest espn --<options>`
  * `baseball ingest weather --<options>`
- [ ] Ensure existing commands still work: `baseball ingest mlb`, `baseball ingest retrosheet`, `baseball ingest statcast`

#### Testing
- [ ] Create unit tests for each new/updated ingestor
- [ ] Test dry-run functionality
- [ ] Test batch processing and conflict resolution
- [ ] Test error handling scenarios
- [ ] Create integration tests that verify data is correctly inserted into raw tables

#### Documentation
- [ ] Update `docs/architecture/source-adapters.md` to document the new ingestors
- [ ] Ensure each source adapter section shows the downloader/ingestor relationship
- [ ] Add notes about raw table structures and any source-specific considerations

## Verification Criteria

- [ ] All source downloaders successfully download data to the configured DATA_DIR
- [ ] All source ingestors can process downloaded files and insert data into the correct raw tables without errors
- [ ] Raw table schemas match the structure of the downloaded data (verified by comparing a sample of ingested rows with source documentation)
- [ ] Ingestors support dry-run mode for validation without database connection
- [ ] Ingestors use batch processing and ON CONFLICT clauses for idempotent operations
- [ ] All raw table SQL scripts are versioned and located in the correct directory (`sql/70_tables_raw/`)
- [ ] The CLI can ingest data from all sources using the pattern `baseball ingest <source> --<options>`
- [ ] No data loss or corruption occurs during the ingest process (verified by row counts and spot checks)
- [ ] All ingestors follow a consistent pattern that developers can easily reuse and extend

## Risks and Mitigations

1. **Risk**: MLB StatsAPI ingestor changes could break existing functionality.
   **Mitigation**: Refactor carefully, ensuring we don't break the existing API until the new raw table ingestors are verified working.

2. **Risk**: Inconsistent data formats between source downloads and ingestor expectations.
   **Mitigation**: Add validation steps in both downloaders and ingestors to check for expected data formats.

3. **Risk**: Missing or incomplete understanding of ESPN/Weather API responses.
   **Mitigation**: Research the actual API responses by examining sample data or making test calls to define appropriate raw tables.

4. **Risk**: Large data volumes causing performance issues.
   **Mitigation**: Implement batch processing in all ingestors and test with realistic data volumes.

5. **Risk**: Schema mismatches due to source changes over time.
   **Mitigation**: Add validation in ingestors to check for expected columns and data types with clear error messages.

## Estimated Effort

This plan outlines the strategic approach to completing the raw data ingestion milestone. The actual implementation work would be performed by an implementation agent (like Forge) following this plan.