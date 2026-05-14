# MLB Stats API Raw DDL Notes

## Source

- **Provider:** MLB via `statsapi.mlb.com/api/v1/`
- **Authority:** Official MLB Stats API docs: <https://statsapi.mlb.com/docs/> and community wrapper `MLB-StatsAPI` (toddrob99/MLB-StatsAPI)
- **Upstream SQL:** None — JSON endpoint responses are the authoritative spec
- **DDL files:** `sql/70_tables_raw/01_raw_mlbstatsapi.sql`

## Design strategy

MLB Stats API returns nested JSON. Raw ingestion uses a JSONB-first approach:
each endpoint family gets its own table with scalar identifier columns extracted
for indexing, plus a `payload` JSONB column preserving the full response.
Do not attempt to fully type all fields at the raw layer — promote to staging/core
layers instead.

## Key tables

### `raw.mlb_schedule`

One row per scheduled game per load.

| Column | Type | Notes |
|--------|------|-------|
| game_pk | bigint | MLB game PK (PK) |
| game_guid | text | Game GUID |
| game_type | text | R=Regular, S=Spring, P=Postseason |
| season | text | Season year |
| game_date | date | Scheduled game date |
| official_date | date | Official game date |
| status_abstract_game_state | text | Preview/Live/Final |
| teams_away_id | integer | Away team ID |
| teams_home_id | integer | Home team ID |
| venue_id | integer | Venue ID |
| loaded_at | timestamptz | Load timestamp |

### `raw.mlb_game_linescore`

One row per game per load.

| Column | Type | Notes |
|--------|------|-------|
| game_pk | bigint | MLB game PK (PK) |
| current_inning | integer | Current inning |
| inning_state | text | Top/Middle/Bottom/End |
| team_away_runs | integer | Away runs |
| team_home_runs | integer | Home runs |
| balls | integer | Ball count |
| strikes | integer | Strike count |
| outs | integer | Out count |
| loaded_at | timestamptz | Load timestamp |

### `raw.mlb_player`

One row per player per load.

| Column | Type | Notes |
|--------|------|-------|
| id | integer | MLB player ID (PK) |
| full_name | text | Full name |
| first_name | text | First name |
| last_name | text | Last name |
| primary_number | text | Jersey number |
| birth_date | date | Birth date |
| active | boolean | Active status |
| primary_position_code | text | Position code |
| bat_side_code | text | L/R/S |
| pitch_hand_code | text | L/R/S |
| loaded_at | timestamptz | Load timestamp |

### `raw.mlb_team`

One row per team per season per load.

| Column | Type | Notes |
|--------|------|-------|
| id | integer | MLB team ID (PK) |
| name | text | Full team name |
| season | integer | Season |
| abbreviation | text | Team abbreviation |
| team_code | text | Team code |
| league_id | integer | League ID |
| division_id | integer | Division ID |
| active | boolean | Active status |
| loaded_at | timestamptz | Load timestamp |

### `raw.mlb_venue`

One row per venue per load.

| Column | Type | Notes |
|--------|------|-------|
| id | integer | Venue ID (PK) |
| name | text | Venue name |
| active | boolean | Active status |
| location_city | text | City |
| location_state | text | State |
| location_latitude | numeric | Latitude |
| location_longitude | numeric | Longitude |
| field_center | integer | Center field distance (ft) |
| capacity | integer | Seating capacity |
| loaded_at | timestamptz | Load timestamp |

### `raw.mlb_standings`

One row per team per standings type per load.

| Column | Type | Notes |
|--------|------|-------|
| standings_id | bigint | Surrogate PK |
| season | text | Season |
| standings_type | text | regularSeason / springTraining / etc. |
| league_id | integer | League ID |
| division_id | integer | Division ID |
| team_id | integer | Team ID |
| wins | integer | Wins |
| losses | integer | Losses |
| win_pct | text | Win percentage |
| loaded_at | timestamptz | Load timestamp |

### `raw.mlb_roster`

One row per player per team roster per load.

| Column | Type | Notes |
|--------|------|-------|
| roster_id | bigint | Surrogate PK |
| team_id | integer | Team ID |
| season | text | Season |
| roster_type | text | 40Man / active / etc. |
| player_id | integer | MLB player ID |
| jersey_number | text | Jersey number |
| position_code | text | Position code |
| status_code | text | Active/IL/etc. |
| loaded_at | timestamptz | Load timestamp |

## Load strategy

- One load per endpoint family per scheduled run
- Schedule, linescore, and standings refresh daily during season
- Player and team tables refresh weekly or on-demand
- Preserve `game_pk` as the cross-source join key (also present in Retrosheet and Statcast)

## Related docs

- [MLB StatsAPI source notes](../sources/mlb-statsapi-source-notes.md)
- [MLB StatsAPI raw schema guide](../sources/mlb-statsapi-raw-schema-guide.md)
