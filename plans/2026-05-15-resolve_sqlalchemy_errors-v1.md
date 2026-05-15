# PLAN TO RESOLVE SQLALCHEMY MODEL/TABLE MISMATCH

## Problem Statement
The SQLAlchemy ORM models in `baseball/db/models.py` define generic raw table classes that don't match the specific raw tables created by the SQL scripts in `sql/70_tables_raw/`. This causes the database validation to fail during `baseball db init` because the expected tables (from models) don't match the actual tables (from SQL).

## Root Cause
- **Models define**: Generic tables like `RawMlbstatsapi`, `RawRetrosheet`, `RawStatcast`, `RawFangraphs`
- **SQL scripts create**: Specific tables like `mlb_schedule`, `mlb_game_linescore`, `retrosheet_events`, `statcast_pitches`, `fangraphs_batting`, etc.
- **Validation compares**: Table names without schema prefix, causing mismatch errors

## Solution Approach
Replace the generic raw table classes in `baseball/db/models.py` with specific classes that match each table defined in the SQL scripts, while preserving:
1. Correct schema (`raw`)
2. Accurate column definitions matching SQL
3. Appropriate indexes and constraints
4. Ingestion metadata columns (`source_url`, `loaded_at`)
5. Existing specific models for ESPN and Weather (they already match)

## Tables to Model
Based on SQL script analysis:

### MLB StatsAPI (from 027_raw_mlbstatsapi.sql)
1. `raw.mlb_schedule`
2. `raw.mlb_game_linescore`
3. `raw.mlb_player`
4. `raw.mlb_team`
5. `raw.mlb_venue`
6. `raw.mlb_standings`
7. `raw.mlb_roster`

### Retrosheet (from individual files)
1. `raw.retrosheet_events` (002_raw_retrosheet_events.sql)
2. `raw.retrosheet_games` (003_raw_retrosheet_games.sql)
3. `raw.retrosheet_rosters` (004_raw_retrosheet_rosters.sql)
4. Plus any lookup tables if needed

### StatCast (from 001_raw_statcast_pitches.sql)
1. `raw.statcast_pitches`

### FanGraphs (from individual files)
1. `raw.fangraphs_batting` (020_raw_fangraphs_batting.sql)
2. `raw.fangraphs_pitching` (021_raw_fangraphs_pitching.sql)

### Lahman (from individual files - optional but recommended for completeness)
1. `raw.lahman_people` (008_raw_lahman_people.sql)
2. `raw.lahman_batting` (005_raw_lahman_batting.sql)
3. `raw.lahman_pitching` (006_raw_lahman_pitching.sql)
4. `raw.lahman_fielding` (007_raw_lahman_fielding.sql)
5. And others as needed

### ESPN and Weather
Already have specific models that match SQL - keep as-is.

## Implementation Steps

### Step 1: Backup Current Models
```bash
cp baseball/db/models.py baseball/db/models.py.backup_before_fix
```

### Step 2: Replace RawMlbstatsapi Class
Replace lines ~332-348 with specific classes for each MLB table:
- RawMlbSchedule
- RawMlbGameLinescore
- RawMlbPlayer
- RawMlbTeam
- RawMlbVenue
- RawMlbStandings
- RawMlbRoster

### Step 3: Replace RawRetrosheet Class
Replace lines ~351-371 with specific classes:
- RawRetrosheetEvents
- RawRetrosheetGames
- RawRetrosheetRosters
- (Optional) lookup table classes if needed

### Step 4: Replace RawStatcast Class
Replace lines ~374-392 with:
- RawStatcastPitches

### Step 5: Replace RawFangraphs Class
Replace lines ~395-412 with:
- RawFangraphsBatting
- RawFangraphsPitching

### Step 6: Verify Column Definitions
For each class, ensure:
- Column types match SQL exactly (TEXT, INTEGER, BOOLEAN, TIMESTAMP, etc.)
- Primary keys are correctly defined
- Nullable constraints match
- Default values match (especially `loaded_at DEFAULT now()`)
- Ingestion metadata columns present (`source_url`, `loaded_at`)

### Step 7: Add Indexes and Constraints
Match indexes and constraints from SQL files:
- Primary keys
- Unique constraints
- Regular indexes for query performance

### Step 8: Test the Fix
```bash
# Test database bootstrap
python -m baseball db init

# Test validation
python -m baseball db validate

# Test end-to-end ingestion for one source
baseball download mlb --season 2024 --sample-size 10
baseball ingest mlb --season 2024 --sample-size 10

# Run tests
pytest tests/test_sources_*ingestor*.py -v
```

## Risk Mitigation
1. **Backup**: Keep original models file for rollback
2. **Incremental**: Fix one source at a time, test after each
3. **Verify**: Check each class against its SQL source
4. **Test**: Validate after each major change

## Expected Outcome
After implementation:
- `baseball db init` runs successfully
- `baseball db validate` passes with zero missing/unexpected tables
- All ingestor tests continue to pass
- End-to-end download/ingest workflows work for all sources
- Foundation is solid for next phases (feature engineering, modeling)

## Files to Modify
- `baseball/db/models.py` (primary)
- Potentially test files if they reference the old generic models

## Estimated Effort
- 2-3 hours for implementation and testing
- Most time spent carefully translating SQL column definitions to SQLAlchemy