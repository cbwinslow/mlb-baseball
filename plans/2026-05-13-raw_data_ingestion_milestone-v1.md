# Raw Data Ingestion Milestone

## Objective

Establish a complete raw data ingestion pipeline for all MLB data sources (MLB StatsAPI, Retrosheet, StatCast, FanGraphs, Lahman, ESPN, Weather) that:
1. Downloads raw data from each source using existing downloaders
2. Ingests the downloaded data into source-specific raw tables in PostgreSQL
3. Uses reusable classes and follows the existing patterns in the codebase
4. Ensures all raw table SQL scripts are present and correct
5. Prepares the foundation for subsequent staging and core table processing

## Implementation Plan

### MLB StatsAPI Source
- [ ] Update `MLBIngestor` to write to raw tables (`raw.mlb_*`) instead of core tables
- [ ] Modify the ingestor to map downloaded JSON/CSV files to the appropriate raw tables defined in `01_raw_mlbstatsapi.sql`
- [ ] Ensure the ingestor handles all raw tables: mlb_schedule, mlb_game, mlb_player, mlb_team, mlb_standings, mlb_boxscore, mlb_roster, mlb_venue
- [ ] Add dry-run support and proper error handling consistent with other ingestors
- [ ] Verify the raw table schema matches the data being downloaded from the MLB StatsAPI

### Retrosheet Source
- [ ] Verify that `RetroEventFileIngestor` correctly writes to `raw.retro_events` and other raw tables
- [ ] Ensure the ingestor handles all raw tables defined in `02_raw_retrosheet.sql` (events, games, rosters, teams, parkcodes, lookups)
- [ ] Confirm that the downloader saves files in the expected format for the ingestor
- [ ] Add support for ingesting game logs and schedule files if not already implemented

### StatCast Source
- [ ] Verify that `StatcastIngestor` correctly writes to `raw.statcast_pitches`
- [ ] Ensure the ingestor handles all columns defined in `03_raw_statcast.sql`
- [ ] Confirm that the downloader saves CSV files in the Baseball Savant export format
- [ ] Add support for ingesting pitcher/batter specific files if needed

### FanGraphs Source
- [ ] Create `FanGraphsIngestor` class in `baseball/sources/fangraphs/ingestor.py`
- [ ] Implement methods to ingest batting, pitching, and fielding statistics CSV files
- [ ] Map CSV columns to the raw tables defined in `04_raw_fangraphs.sql` (fg_batting, fg_pitching, fg_fielding, fg_team_batting, fg_team_pitching)
- [ ] Follow the same pattern as existing ingestors (dry-run support, batch upserts, error handling)
- [ ] Ensure the ingestor uses the source URL and loaded_at metadata fields

### Lahman Source
- [ ] Create `LahmanIngestor` class in `baseball/sources/lahman/ingestor.py`
- [ ] Implement methods to ingest each Lahman CSV table (people, batting, pitching, fielding, etc.)
- [ ] Map CSV columns to the corresponding raw tables defined in the lahman SQL files (005_raw_lahman_batting.sql through 019_raw_lahman_managers.sql)
- [ ] Follow the same pattern as existing ingestors
- [ ] Handle the Lahman database versioning and extract the correct CSV files from the downloaded ZIP

### ESPN Source
- [ ] Create raw table SQL script for ESPN data in `sql/70_tables_raw/` (e.g., `25_raw_espn.sql`)
- [ ] Define tables for scores, standings, and other ESPN API endpoints based on the downloader output
- [ ] Create `ESPNIngestor` class in `baseball/sources/espn/ingestor.py`
- [ ] Implement methods to ingest JSON data from the ESPN API into the raw tables
- [ ] Follow the same pattern as existing ingestors

### Weather Source
- [ ] Create raw table SQL script for weather data in `sql/70_tables_raw/` (e.g., `26_raw_weather.sql`)
- [ ] Define tables for game-time weather data based on the downloader output
- [ ] Create `WeatherIngestor` class in `baseball/sources/weather/ingestor.py`
- [ ] Implement methods to ingest weather data into the raw tables
- [ ] Follow the same pattern as existing ingestors

### Cross-Cutting Tasks
- [ ] Ensure all ingestors inherit from a common base class or interface for consistency
- [ ] Verify that all raw table SQL scripts include proper headers with source, URL, access date, and attribution
- [ ] Add indexes to raw tables as appropriate for query performance
- [ ] Update the `baseball/sources/registry.py` to include all new ingestors
- [ ] Ensure the CLI `ingest` command can handle all new source types
- [ ] Add integration tests for each new ingestor to verify data loading
- [ ] Document the raw data ingestion process in the architecture documentation

## Verification Criteria

- [ ] All source downloaders successfully download data to the configured DATA_DIR
- [ ] All source ingestors can process downloaded files and insert data into the correct raw tables without errors
- [ ] Raw table schemas match the structure of the downloaded data (verified by comparing a sample of ingested rows with source documentation)
- [ ] Ingestors support dry-run mode for validation without database connection
- [ ] Ingestors use batch processing and ON CONFLICT clauses for idempotent operations
- [ ] All raw table SQL scripts are versioned and located in the correct directory (`sql/70_tables_raw/`)
- [ ] The CLI can ingest data from all sources using the pattern `baseball ingest <source> --<options>`
- [ ] No data loss or corruption occurs during the ingest process (verified by row counts and spot checks)

## Potential Risks and Mitigations

1. **Risk**: MLB StatsAPI ingestor currently writes to core tables, requiring significant changes.
   **Mitigation**: Refactor the ingestor to write to raw tables first, then create a separate process (to be developed later) to move data from raw to staging to core tables.

2. **Risk**: Inconsistent naming or structure between downloader output and ingestor expectations.
   **Mitigation**: Create clear documentation for each source's expected file format and validate it in the downloader and ingestor.

3. **Risk**: Missing raw table definitions for ESPN and Weather sources.
   **Mitigation**: Research the ESPN and Weather API responses to define appropriate raw tables before implementing the ingestors.

4. **Risk**: Large data volumes causing memory issues during ingest.
   **Mitigation**: Implement batch processing in all ingestors (similar to existing Retrosheet and Statcast ingestors) to manage memory usage.

5. **Risk**: Schema mismatches between raw tables and actual data due to source changes.
   **Mitigation**: Add validation steps in the ingestors to check for expected columns and data types, with clear error messages.

## Alternative Approaches

1. **Alternative**: Use a single generic ingestor that dynamically maps any source data to raw tables based on configuration.
   **Trade-offs**: More flexible but less type-safe and harder to debug; loses the benefits of source-specific validation and optimization.

2. **Alternative**: Ingest directly into staging tables, skipping the raw layer entirely.
   **Trade-offs**: Simpler initially but violates the raw-first architecture principle, making it harder to reprocess data or track changes to source formats.

3. **Alternative**: Use an ORM or database abstraction layer for ingest instead of raw SQL.
   **Trade-offs**: Reduces control over performance and database-specific features; increases complexity and potential for ORM-related issues.