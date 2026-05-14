# Raw Data Ingestion Milestone Plan

## Objective

Complete the raw data ingestion layer for all MLB data sources by:
1. Ensuring all source data is properly stored in source-specific raw tables in PostgreSQL
2. Creating missing ingestors for FanGraphs, Lahman, ESPN, and Weather sources
3. Fixing the MLB StatsAPI ingestor to write to raw tables instead of core tables
4. Verifying all raw table schemas match source data specifications
5. Establishing a consistent pattern for all ingestors that can be reused by developers

## Implementation Plan

### Phase 1: Fix Existing Ingestors

#### MLB StatsAPI Ingestor
- [ ] Modify `MLBIngestor` in `baseball/sources/mlb/ingestor.py` to write to raw tables (`raw.mlb_*`) instead of `baseball.mlb_schedule`
- [ ] Update column mappings to match the raw table definitions in `01_raw_mlbstatsapi.sql`
- [ ] Ensure all raw tables are handled: mlb_schedule, mlb_game, mlb_player, mlb_team, mlb_standings, mlb_boxscore, mlb_venue, mlb_roster
- [ ] Maintain dry-run support and batch processing capabilities

#### Retrosheet Ingestor
- [ ] Verify `RetroEventFileIngestor` in `baseball/sources/retrosheet/ingestor.py` correctly writes to all raw tables defined in `02_raw_retrosheet.sql`
- [ ] Ensure it handles events, games, rosters, teams, parkcodes, and lookup tables
- [ ] Confirm proper batch processing and conflict resolution

#### StatCast Ingestor
- [ ] Verify `StatcastIngestor` in `baseball/sources/statcast/ingestor.py` correctly writes to `raw.statcast_pitches`
- [ ] Ensure all columns from `03_raw_statcast.sql` are properly mapped
- [ ] Confirm batch upsert functionality works correctly

### Phase 2: Create Missing Ingestors

#### FanGraphs Ingestor
- [ ] Create `FanGraphsIngestor` class in `baseball/sources/fangraphs/ingestor.py`
- [ ] Implement methods to ingest:
  * Batting statistics (maps to `raw.fg_batting`)
  * Pitching statistics (maps to `raw.fg_pitching`)
  * Fielding statistics (maps to `raw.fg_fielding`)
  * Team batting/pitching (if needed)
- [ ] Follow the same pattern as existing ingestors:
  * Dry-run support
  * Batch processing with ON CONFLICT clauses
  * Proper error handling and logging
  * Source URL and loaded_at metadata tracking
- [ ] Map CSV columns from FanGraphs exports to the appropriate raw table columns

#### Lahman Ingestor
- [ ] Create `LahmanIngestor` class in `baseball/sources/lahman/ingestor.py`
- [ ] Implement methods to ingest each Lahman CSV table:
  * People (maps to `008_raw_lahman_people.sql`)
  * Batting (maps to `005_raw_lahman_batting.sql`)
  * Pitching (maps to `006_raw_lahman_pitching.sql`)
  * Fielding (maps to `007_raw_lahman_fielding.sql`)
  * And all other Lahman tables found in `sql/70_tables_raw/`
- [ ] Handle reading from extracted CSV files in the Lahman ZIP structure
- [ ] Follow the same ingestor pattern as other sources

#### ESPN Ingestor
- [ ] First, create raw table SQL script for ESPN data:
  * Add `25_raw_espn.sql` to `sql/70_tables_raw/`
  * Define tables for scores, standings, and other ESPN API endpoints based on actual API responses
- [ ] Create `ESPNIngestor` class in `baseball/sources/espn/ingestor.py`
- [ ] Implement methods to ingest JSON data from ESPN API into raw tables
- [ ] Follow the same pattern as existing ingestors

#### Weather Ingestor
- [ ] First, create raw table SQL script for weather data:
  * Add `26_raw_weather.sql` to `sql/70_tables_raw/`
  * Define tables for game-time weather data based on the weather API responses
- [ ] Create `WeatherIngestor` class in `baseball/sources/weather/ingestor.py`
- [ ] Implement methods to ingest weather data into raw tables
- [ ] Follow the same pattern as existing ingestors

### Phase 3: Schema Verification and Standardization

#### Raw Table Verification
- [ ] For each source, verify that the raw table SQL scripts in `sql/70_tables_raw/` accurately represent the source data structure
- [ ] Check that all necessary columns are present and correctly typed
- [ ] Ensure proper indexing for query performance
- [ ] Verify that header comments include source, URL, access date, and attribution as per documentation standards

#### Ingestor Standardization
- [ ] Ensure all ingestors follow a consistent interface:
  * `__init__(db_connection: Optional[Engine] = None)`
  * Dry-run detection and handling
  * Batch processing capabilities
  * Consistent error handling and logging
  * Return `IngestResult` objects with standard fields
- [ ] Consider creating a base `BaseIngestor` class to enforce consistency
- [ ] Verify all ingestors properly handle the `source_file` and `loaded_at` metadata fields

#### Registry and CLI Integration
- [ ] Update `baseball/sources/registry.py` to include all new ingestors
- [ ] Ensure the CLI `ingest` command can handle all source types:
  * `baseball ingest fangraphs --<options>`
  * `baseball ingest lahman --<options>`
  * `baseball ingest espn --<options>`
  * `baseball ingest weather --<options>`
- [ ] Verify existing commands still work: `baseball ingest mlb`, `baseball ingest retrosheet`, `baseball ingest statcast`

### Phase 4: Testing and Validation

#### Unit Tests
- [ ] Create unit tests for each new ingestor
- [ ] Test dry-run functionality
- [ ] Test batch processing and conflict resolution
- [ ] Test error handling scenarios

#### Integration Tests
- [ ] Create integration tests that:
  * Download sample data (or use fixtures)
  * Ingest the data into a test database
  * Verify the data was correctly inserted into raw tables
  * Check row counts and sample data integrity

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

## Potential Risks and Mitigations

1. **Risk**: MLB StatsAPI ingestor currently writes to core tables, requiring changes that could affect existing functionality.
   **Mitigation**: Refactor incrementally, ensuring backward compatibility where possible, and create a separate process (to be developed later) to move data from raw to staging to core tables.

2. **Risk**: Inconsistent data formats between source downloads and ingestor expectations.
   **Mitigation**: Create clear documentation for each source's expected file format and add validation steps in both downloaders and ingestors.

3. **Risk**: Missing or incomplete raw table definitions for ESPN and Weather sources.
   **Mitigation**: Research the actual API responses by making sample calls to define appropriate raw tables before implementing the ingestors.

4. **Risk**: Large data volumes causing memory or performance issues during ingest.
   **Mitigation**: Implement batch processing in all ingestors (similar to existing Retrosheet and Statcast ingestors) and monitor performance with realistic data volumes.

5. **Risk**: Schema mismatches between raw tables and actual data due to source changes over time.
   **Mitigation**: Add validation steps in the ingestors to check for expected columns and data types, with clear error messages that help identify when sources have changed.

## Alternative Approaches

1. **Alternative**: Use a single generic ingestor that dynamically maps any source data to raw tables based on configuration.
   **Trade-offs**: More flexible but less type-safe and harder to debug; loses the benefits of source-specific validation and optimization that we've already implemented for MLB, Retrosheet, and StatCast.

2. **Alternative**: Ingest directly into staging tables, skipping the raw layer entirely.
   **Trade-offs**: Simpler initially but violates the raw-first architecture principle, making it harder to reprocess data or track changes to source formats. The raw layer provides a valuable audit trail and allows for reprocessing with different transformations.

3. **Alternative**: Use an ORM or database abstraction layer for ingest instead of raw SQL.
   **Trade-offs**: Reduces control over performance and database-specific features; increases complexity and potential for ORM-related issues. The current approach using raw SQL gives us precise control over the ingest process and performance characteristics.

The chosen approach maintains consistency with the existing codebase architecture while ensuring completeness and correctness for the raw data ingestion milestone.