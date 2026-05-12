# Raw Tables (`sql/70_tables_raw/`)

This directory contains `CREATE TABLE` DDL statements for ingesting data from all sources **as-is**.
No transformations are applied at the raw layer — every field from the original source is preserved.

## Sources

| File | Source | Description |
|------|--------|-------------|
| `001_raw_statcast_pitches.sql` | Baseball Savant / Statcast | Pitch-level data, all Statcast fields |
| `002_raw_retrosheet_events.sql` | Retrosheet | Play-by-play event file records |
| `003_raw_retrosheet_games.sql` | Retrosheet | Game-level info records |
| `004_raw_retrosheet_rosters.sql` | Retrosheet | Roster/player records |
| `005_raw_lahman_batting.sql` | Lahman DB | Season batting stats |
| `006_raw_lahman_pitching.sql` | Lahman DB | Season pitching stats |
| `007_raw_lahman_fielding.sql` | Lahman DB | Season fielding stats |
| `008_raw_lahman_people.sql` | Lahman DB | Player biographical data |
| `009_raw_lahman_teams.sql` | Lahman DB | Team season records |
| `010_raw_lahman_salaries.sql` | Lahman DB | Player salaries |
| `011_raw_lahman_awards.sql` | Lahman DB | Awards data |
| `012_raw_lahman_allstar.sql` | Lahman DB | All-Star game appearances |
| `013_raw_lahman_appearances.sql` | Lahman DB | Player appearances by position |
| `014_raw_lahman_batting_post.sql` | Lahman DB | Postseason batting |
| `015_raw_lahman_pitching_post.sql` | Lahman DB | Postseason pitching |
| `016_raw_lahman_fielding_post.sql` | Lahman DB | Postseason fielding |
| `017_raw_lahman_series_post.sql` | Lahman DB | Postseason series results |
| `018_raw_lahman_managers.sql` | Lahman DB | Manager records |
| `019_raw_lahman_parks.sql` | Lahman DB | Park data |
| `020_raw_fangraphs_batting.sql` | FanGraphs (pybaseball) | Season batting stats |
| `021_raw_fangraphs_pitching.sql` | FanGraphs (pybaseball) | Season pitching stats |
| `022_raw_bbref_batting.sql` | Baseball Reference (pybaseball) | Batting stats |
| `023_raw_bbref_pitching.sql` | Baseball Reference (pybaseball) | Pitching stats |
| `024_raw_bbref_schedule.sql` | Baseball Reference (pybaseball) | Schedule and results |
| `025_raw_playerid_map.sql` | Chadwick/pybaseball | Cross-source player ID mapping |

## Design Philosophy

- All tables live in the `raw` schema
- Every column from the source is retained, typed as broadly as possible (TEXT for strings, NUMERIC for numbers, BOOLEAN, TIMESTAMP, etc.)
- A `_ingested_at` audit timestamp is added to every table
- A `_source_file` TEXT column tracks the originating file/batch where applicable
- No foreign keys enforced at raw layer — data is ingested first, validated later
- Deprecated fields from Statcast are retained with a `_deprecated` suffix in the column name
