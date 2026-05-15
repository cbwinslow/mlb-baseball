# Database Bootstrap Plan for Raw Data Ingestion Milestone

## Objective

Successfully bootstrap the PostgreSQL database for the baseball analytics platform, ensuring all raw tables, indexes, constraints, and procedures are correctly created from the SQL schema files. Validate that the database schema matches the expected structure for all seven data sources (MLB StatsAPI, Retrosheet, StatCast, FanGraphs, Lahman, ESPN, Weather) and that the bootstrap process is repeatable and idempotent.

## Implementation Plan

- [ ] Verify PostgreSQL service is running and accessible on localhost:5432
- [ ] Confirm the 'baseball' database exists; create if necessary
- [ ] Verify the 'baseball' database user exists with appropriate privileges; create if necessary
- [ ] Set DATABASE_URL environment variable correctly pointing to the local database
- [ ] Install Python dependencies in a virtual environment (if not already done)
- [ ] Run the database bootstrap command: `python -m baseball db init`
- [ ] Capture and analyze any error messages during bootstrap
- [ ] If bootstrap fails, diagnose connection issues (credentials, network, PostgreSQL configuration)
- [ ] If bootstrap succeeds, run schema validation: `python -m baseball db validate`
- [ ] Verify all expected raw tables are present:
  - mlb_schedule, mlb_game_linescore (from MLB StatsAPI)
  - retrosheet_events, retrosheet_games, retrosheet_rosters (from Retrosheet)
  - statcast_pitches (from StatCast)
  - fg_batting, fg_pitching, fg_fielding (from FanGraphs)
  - lahman_people, lahman_batting, lahman_pitching, lahman_fielding, and other Lahman tables
  - espn_events, espn_competitions, espn_teams, espn_venues, espn_broadcasts, espn_odds (from ESPN)
  - weather_stations, weather_forecasts, weather_periods (from Weather)
- [ ] Check that primary keys, foreign keys, indexes, and constraints are properly defined
- [ ] Ensure the bootstrap process is idempotent by running `baseball db init` a second time without errors
- [ ] Document any discrepancies between expected and actual schema
- [ ] Update the bootstrap process or SQL files if necessary to correct issues
- [ ] Create a summary document of the bootstrap process and results

## Verification Criteria

- [ ] The `baseball db init` command completes successfully with output indicating "SQL bootstrap completed successfully"
- [ ] The `baseball db validate` command passes with no missing or extra tables reported
- [ ] All 7 data sources have their corresponding raw tables created in the database
- [ ] Each raw table has at least a primary key defined
- [ ] Foreign key relationships are established where appropriate (e.g., between game and team tables)
- [ ] Indexes are created on commonly queried columns (e.g., game_id, date, team_id)
- [ ] Running the bootstrap a second time does not produce errors or duplicate objects (idempotent)
- [ ] The database connection health check passes (`baseball db status` shows connection OK)
- [ ] A summary document is created detailing the bootstrap process, any issues encountered, and resolutions

## Potential Risks and Mitigations

1. **Risk**: PostgreSQL service not running or inaccessible
   Mitigation: Check PostgreSQL service status with `sudo systemctl status postgresql` (Linux) or appropriate OS command; start service if needed

2. **Risk**: Database or user does not exist
   Mitigation: Create database and user with appropriate privileges using PostgreSQL commands before bootstrap

3. **Risk**: Connection string format or credentials incorrect in .env file
   Mitigation: Verify DATABASE_URL format matches `postgresql+psycopg://username:password@host:port/database`; test connection with `psql` command

4. **Risk**: SQL files contain syntax errors or execution order issues
   Mitigation: Examine bootstrap logs to identify failing SQL file; fix SQL syntax or adjust file ordering in sql/ directory

5. **Risk**: Insufficient privileges for the database user to create tables
   Mitigation: Grant necessary privileges (CREATE, CONNECT, TEMPORARY) to the database user on the target database

6. **Risk**: Bootstrap process not idempotent due to missing IF NOT EXISTS or ON CONFLICT clauses
   Mitigation: Review SQL files for proper use of IF NOT EXISTS for CREATE statements and appropriate conflict resolution

## Alternative Approaches

1. **Manual SQL Execution**: Instead of using the bootstrap script, manually execute SQL files in order using `psql` command line tool for greater control and debugging visibility
2. **Dockerized PostgreSQL**: Use Docker to run a PostgreSQL instance with predefined credentials and database, ensuring consistent environment across machines
3. **Schema Management Tool**: Use a dedicated schema migration tool like Alembic (already integrated) or Flyway for more advanced versioning and rollback capabilities
4. **Partial Bootstrap**: Bootstrap only specific schema sections (e.g., only raw tables) for faster iteration during development
5. **Validate First**: Run schema validation before bootstrap to understand current state, then apply only missing SQL files
