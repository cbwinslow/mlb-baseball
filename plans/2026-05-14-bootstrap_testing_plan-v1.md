# Bootstrap Testing Plan

## Objective
Test the database bootstrap protocol to ensure it correctly sets up all tables, indexes, constraints, and procedures for the raw data ingestion milestone.

## Implementation Plan

- [ ] Verify PostgreSQL is running and accessible
- [ ] Check that the .env file contains the correct DATABASE_URL
- [ ] Run the bootstrap command: `python -m baseball db init`
- [ ] Verify the command completes without errors
- [ ] Check the output for successful table creation messages
- [ ] Run schema validation: `python -m baseball db validate`
- [ ] Confirm validation passes with all expected tables found
- [ ] Verify raw tables for all sources are created:
    - mlb: raw.mlb_schedule, raw.mlb_game_linescore
    - retrosheet: raw.retrosheet_events, raw.retrosheet_games, raw.retrosheet_rosters
    - statcast: raw.statcast_pitches
    - fangraphs: raw.fg_batting, raw.fg_pitching, raw.fg_fielding
    - lahman: raw.lahman_people, raw.lahman_batting, raw.lahman_pitching, raw.lahman_fielding, etc.
    - espn: raw.espn_events, raw.espn_competitions, raw.espn_teams, raw.espn_venues, raw.espn_broadcasts, raw.espn_odds
    - weather: raw.weather_stations, raw.weather_forecasts, raw.weather_periods
- [ ] Check that primary keys are defined on each table
- [ ] Verify foreign key relationships where applicable
- [ ] Confirm indexes are created for common query columns (e.g., game_id, date, team_id)
- [ ] Test idempotency by running the bootstrap again and verifying no errors
- [ ] Test the `--drop-existing` flag to ensure it correctly drops and recreates tables
- [ ] Verify that the schema validation script correctly reports the expected vs found tables

## Verification Criteria

- [ ] The `baseball db init` command runs successfully without errors
- [ ] All SQL files in the `sql/` directory are executed in the correct order
- [ ] The database schema includes all expected raw tables (mlb, retrosheet, statcast, fangraphs, lahman, espn, weather)
- [ ] Primary keys, foreign keys, indexes, and constraints are properly created
- [ ] The schema validation passes (via `baseball db validate`)
- [ ] The bootstrap is idempotent (can be run multiple times without causing errors)
- [ ] The `--drop-existing` flag works as expected

## Potential Risks and Mitigations

1. **[Risk: Incorrect SQL path resolution]**
   Mitigation: Verify the SQL path resolution in `baseball/cli/commands/db.py` points to the correct directory (three levels up from the file).

2. **[Risk: Missing tables due to SQL errors]**
   Mitigation: Check the output of the bootstrap for any error messages and validate each SQL file individually if needed.

3. **[Risk: Schema validation false positives]**
   Mitigation: Ensure the validation script in `baseball/db/schema.py` correctly compares expected vs found tables.

## Alternative Approaches

1. [Alternative approach]: Use a Docker container for PostgreSQL to ensure a clean environment for testing.
   Trade-offs: Requires Docker setup but provides isolation and reproducibility.

2. [Alternative approach]: Create a separate test database for bootstrap testing to avoid interfering with development data.
   Trade-offs: Requires additional configuration but prevents data loss.
