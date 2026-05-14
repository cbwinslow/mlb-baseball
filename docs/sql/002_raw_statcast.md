# Statcast / Baseball Savant Raw DDL Notes

## Source

- **Provider:** MLB / Baseball Savant via `pybaseball` (`statcast()` function)
- **Authority:** Official CSV export docs at <https://baseballsavant.mlb.com/statcast_search>
- **Upstream SQL:** None — CSV column headers are the authoritative spec
- **DDL files:** `sql/70_tables_raw/001_raw_statcast_pitches.sql`, `sql/70_tables_raw/03_raw_statcast.sql`

## Design strategy

Statcast data arrives as flat CSV exports. Each row is one pitch/plate appearance event.
Raw ingestion uses a typed relational table that mirrors the official CSV column layout.
No JSONB blob is needed because the source format is tabular and column-stable within a season.

## Key tables

### `raw.statcast_pitches`

One row per pitch event.

| Column | Type | Notes |
|--------|------|-------|
| pitch_id | uuid | Surrogate PK (load-assigned) |
| game_pk | bigint | MLB game identifier |
| game_date | date | Game date |
| batter | integer | MLB batter ID |
| pitcher | integer | MLB pitcher ID |
| events | text | Plate appearance outcome |
| description | text | Pitch description |
| pitch_type | text | Pitch type code |
| release_speed | numeric | Pitch velocity (mph) |
| release_spin_rate | integer | Spin rate (rpm) |
| release_extension | numeric | Extension (ft) |
| pfx_x | numeric | Horizontal movement (ft) |
| pfx_z | numeric | Vertical movement (ft) |
| plate_x | numeric | Horizontal plate location |
| plate_z | numeric | Vertical plate location |
| launch_speed | numeric | Exit velocity (mph) |
| launch_angle | integer | Launch angle (degrees) |
| hit_distance_sc | integer | Hit distance (ft) |
| estimated_ba_using_speedangle | numeric | xBA |
| estimated_woba_using_speedangle | numeric | xwOBA |
| woba_value | numeric | wOBA value for outcome |
| babip_value | numeric | BABIP value |
| iso_value | numeric | ISO value |
| launch_speed_angle | integer | Sweet spot category |
| at_bat_number | integer | At bat number in game |
| pitch_number | integer | Pitch number in at bat |
| inning | integer | Inning |
| inning_topbot | text | Top/Bot |
| home_team | text | Home team abbreviation |
| away_team | text | Away team abbreviation |
| outs_when_up | integer | Outs when batter came up |
| balls | integer | Ball count |
| strikes | integer | Strike count |
| on_1b | integer | Runner on 1B (player ID) |
| on_2b | integer | Runner on 2B (player ID) |
| on_3b | integer | Runner on 3B (player ID) |
| stand | text | Batter handedness |
| p_throws | text | Pitcher handedness |
| if_fielding_alignment | text | Infield alignment |
| of_fielding_alignment | text | Outfield alignment |
| loaded_at | timestamptz | Row load timestamp |
| load_id | uuid | Batch load identifier |

## Load strategy

- Load via `pybaseball.statcast(start_dt, end_dt)` by date range
- De-duplicate on `(game_pk, at_bat_number, pitch_number)` before inserting
- Track load batches in a companion `raw.statcast_load_batches` metadata table
- Expect ~700 rows per game; ~2,500 games per season → ~1.75M rows/season

## Schema drift notes

- Baseball Savant adds new model columns (e.g., arm angle, stuff+) each year
- Always run a column diff between new pybaseball output and current table before loading a new season
- Use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` to extend the table

## Related docs

- [Statcast source notes](../sources/statcast-source-notes.md)
- [Statcast raw schema guide](../sources/statcast-raw-schema-guide.md)
