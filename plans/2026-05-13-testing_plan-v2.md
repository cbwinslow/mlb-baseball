# Testing Plan for Raw Data Ingestion Milestone

## Overview
This document outlines a comprehensive testing plan to verify that all components implemented for the raw data ingestion milestone are working correctly. The plan covers testing downloaders, ingestors, CLI commands, and end-to-end workflows for all seven data sources: MLB StatsAPI, Retrosheet, StatCast, FanGraphs, Lahman, ESPN, and Weather.

## Test Environment Setup
Before running tests, ensure:
1. PostgreSQL 16 is running and accessible
2. Environment variables are set:
   - `DATABASE_URL`: PostgreSQL connection string
   - `DATA_DIR`: Root directory for test data (e.g., `/tmp/baseball_test_data`)
3. Python dependencies are installed (`pip install -e .`)
4. Test directories are created and writable

## Testing Strategy
We'll test at three levels:
1. **Unit Tests**: Individual downloader and ingestor classes
2. **Integration Tests**: CLI commands and service layer
3. **End-to-End Tests**: Complete download → ingest workflows

Each test should verify:
- Successful execution without errors
- Correct data transformation and storage
- Proper handling of edge cases (dry-run mode, missing files, etc.)
- Consistency with expected patterns and interfaces

## Test Plan by Component

### 1. MLB StatsAPI Tests

#### Downloader Tests
- Test `download_schedule()` with valid season
- Test `download_game()` with valid game_pk
- Verify files are saved to correct location with expected naming
- Test error handling for invalid parameters

#### Ingestor Tests
- Test `ingest_schedule()` with sample CSV data
- Test `ingest_game()` with sample JSON data
- Verify data is inserted into `raw.mlb_schedule` and `raw.mlb_game_linescore`
- Test dry-run mode (no DB connection) - should not write to DB
- Test UPSERT behavior (re-running same data doesn't create duplicates)

#### CLI Tests
- Test `baseball ingest mlbstatsapi --season 2024` with sample data
- Verify output shows correct ingestion results
- Test with non-existent data directory (should show helpful error)

### 2. Retrosheet Tests

#### Downloader Tests
- Test event file download for valid season/team
- Test game log download for valid season/league
- Verify correct file types (.ev? for events, GL*.txt for gamelogs)

#### Ingestor Tests
- Test `ingest_event_file()` with sample event data
- Test `ingest_game_logs()` with sample gamelog data
- Verify data inserted into correct raw tables:
  - `raw.retrosheet_events`
  - `raw.retrosheet_games`
  - `raw.retrosheet_rosters`
- Test different ingest types: events, gamelogs, all

#### CLI Tests
- Test `baseball ingest retrosheet --season 2024 --type events`
- Test `baseball ingest retrosheet --season 2024 --type gamelogs`
- Test `baseball ingest retrosheet --season 2024 --type all`

### 3. StatCast Tests

#### Downloader Tests
- Test season-based download
- Test date-range based download
- Verify CSV files are saved correctly

#### Ingestor Tests
- Test `ingest_season()` with sample StatCast CSV
- Verify data inserted into `raw.statcast_pitches`
- Test dry-run mode

#### CLI Tests
- Test `baseball ingest statcast --season 2024`
- Test `baseball ingest statcast --start-date 2024-04-01 --end-date 2024-04-02`

### 4. FanGraphs Tests

#### Downloader Tests
- Test batting statistics download for valid season
- Test pitching statistics download for valid season
- Test fielding statistics download for valid season
- Verify CSV files are saved with correct naming

#### Ingestor Tests
- Test `ingest_batting_stats()` with sample batting CSV
- Test `ingest_pitching_stats()` with sample pitching CSV
- Test `ingest_fielding_stats()` with sample fielding CSV
- Verify data inserted into correct raw tables:
  - `raw.fg_batting`
  - `raw.fg_pitching`
  - `raw.fg_fielding`
- Test dry-run mode
- Verify column mapping works correctly (especially for percentage columns)

#### CLI Tests
- Test `baseball ingest fangraphs --data-type batting --season 2024`
- Test `baseball ingest fangraphs --data-type pitching --season 2024`
- Test `baseball ingest fangraphs --data-type fielding --season 2024`
- Test invalid data type (should show error and list valid types)

### 5. Lahman Tests

#### Downloader Tests
- Test Lahman ZIP download and extraction
- Verify all expected CSV files are extracted to correct location

#### Ingestor Tests
- Test `ingest_people()` with sample People.csv
- Test `ingest_batting()` with sample Batting.csv
- Test `ingest_pitching()` with sample Pitching.csv
- Test `ingest_fielding()` with sample Fielding.csv
- Test a few additional tables (teams, appearances, salaries, etc.)
- Verify data inserted into correct `raw.lahman_*` tables
- Test dry-run mode
- Verify conflict resolution works (re-running same data doesn't create duplicates)

#### CLI Tests
- Test `baseball ingest lahman --data-type people`
- Test `baseball ingest lahman --data-type batting`
- Test `baseball ingest lahman --data-type pitching`
- Test `baseball ingest lahman --data-type fielding`
- Test invalid data type (should show error and list valid types)

### 6. ESPN Tests

#### Downloader Tests
- Test scoreboard download for valid date range
- Verify JSON files are saved with correct naming
- Test single day and date range downloads

#### Ingestor Tests
- Test `ingest_scoreboard()` with sample ESPN JSON
- Verify data inserted into correct raw tables:
  - `raw.espn_events`
  - `raw.espn_competitions`
  - `raw.espn_teams`
  - `raw.espn_venues`
  - `raw.espn_broadcasts`
  - `raw.espn_odds` (if available in sample)
- Test dry-run mode
- Verify date parsing and foreign key relationships

#### CLI Tests
- Test `baseball ingest espn --start-date 2024-04-01 --end-date 2024-04-02`
- Test `baseball ingest espn --start-date 2024-04-01` (single day)
- Test with non-existent data directory

### 7. Weather Tests

#### Downloader Tests
- Test forecast download for valid date range
- Verify JSON files are saved with correct naming
- Test single day and date range downloads

#### Ingestor Tests
- Test `ingest_forecast()` with sample NOAA weather JSON
- Verify data inserted into correct raw tables:
  - `raw.weather_stations`
  - `raw.weather_forecasts`
  - `raw.weather_periods`
- Test dry-run mode
- Verify timestamp parsing and relationships between tables

#### CLI Tests
- Test `baseball ingest weather --start-date 2024-04-01 --end-date 2024-04-02`
- Test `baseball ingest weather --start-date 2024-04-01` (single day)
- Test with non-existent data directory

## End-to-End Workflow Tests

### Complete Download → Ingest Cycles
For each source, test the complete workflow:
1. Download sample data (use small date ranges/seasons for efficiency)
2. Ingest the downloaded data
3. Verify data appears correctly in raw tables
4. Test idempotency by running ingest again (should update existing rows, not duplicate)

### Cross-Source Consistency Tests
Verify all sources follow the same patterns:
- All ingestors have `__init__(db_connection: Optional[Engine] = None)`
- All ingestors properly detect and handle dry-run mode
- All ingestors return `IngestResult` objects with consistent fields
- All ingestors use batch processing and UPSERT for efficiency
- All CLI commands follow the same naming and parameter patterns

### Error Handling Tests
Test that all components handle errors gracefully:
- Missing input files
- Invalid data formats
- Database connection failures
- Network timeouts (for downloaders)
- Invalid parameters

## Success Criteria
All tests should pass with:
1. Zero unhandled exceptions
2. Correct data stored in expected raw tables
3. Proper dry-run behavior (no DB writes when connection is None)
4. Helpful error messages for user-facing failures
5. Consistent behavior across all data sources
6. Idempotent operations (safe to re-run)

## Test Data Recommendations
Use minimal, representative test data:
- MLB: 1-2 games from a recent season
- Retrosheet: 1 event file, 1 gamelog file
- StatCast: Small CSV subset (10-20 pitches)
- FanGraphs: Small CSV subset (5-10 players per type)
- Lahman: Small CSV subsets for each table type
- ESPN: 1-2 days of scoreboard data
- Weather: 1-2 days of forecast data

## Automation Suggestion
Consider creating a test script that:
1. Sets up temporary directories
2. Runs download commands with test parameters
3. Runs ingest commands on the downloaded data
4. Verifies results in database
5. Cleans up test data
6. Reports pass/fail status for each source

This testing plan ensures that all components of the raw data ingestion milestone are thoroughly validated and working correctly before moving on to subsequent development phases.