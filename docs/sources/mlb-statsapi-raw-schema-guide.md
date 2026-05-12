# MLB Stats API Raw Schema Guide

## Strategy

Because MLB Stats API responses are endpoint-specific JSON payloads with varying shapes, the raw layer should use JSONB payload tables keyed by endpoint family. Extract only stable scalar identifiers into typed columns alongside the JSONB blob. Do not attempt to flatten all endpoint fields into wide typed tables in the raw layer.

## Raw table families

### raw_mlb_schedule

One row per game returned by the schedule endpoint.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| game_pk | bigint | MLB game primary key |
| game_date | date | Scheduled game date |
| game_type | text | R/P/S/E/A |
| season | integer | Season year |
| status_code | text | Game status code |
| status_detail | text | Game status detail text |
| away_team_id | integer | Away team MLB ID |
| home_team_id | integer | Home team MLB ID |
| away_score | integer | Away team score (null if not final) |
| home_score | integer | Home team score (null if not final) |
| venue_id | integer | Venue MLB ID |
| double_header | text | Y/N/S |
| game_number | integer | Doubleheader game number |
| payload | jsonb | Full schedule game object from API |
| retrieved_at | timestamptz | Load timestamp |

### raw_mlb_game_feed

One row per game live feed snapshot.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| game_pk | bigint | MLB game primary key |
| game_date | date | Game date |
| feed_type | text | live / boxscore / linescore / playByPlay |
| status_code | text | Game status at time of retrieval |
| payload | jsonb | Full feed payload from API |
| retrieved_at | timestamptz | Load timestamp |

### raw_mlb_people

One row per player retrieval.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| person_id | integer | MLB player ID |
| full_name | text | Player full name |
| active | boolean | Active roster status |
| primary_position_code | text | Position code |
| bat_side_code | text | R/L/S |
| pitch_hand_code | text | R/L/S |
| mlb_debut_date | date | MLB debut date |
| payload | jsonb | Full player object from API |
| retrieved_at | timestamptz | Load timestamp |

### raw_mlb_teams

One row per team retrieval.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| team_id | integer | MLB team ID |
| season | integer | Season year |
| name | text | Team full name |
| abbreviation | text | Team abbreviation |
| team_code | text | Team code |
| location_name | text | City name |
| league_id | integer | League MLB ID |
| division_id | integer | Division MLB ID |
| venue_id | integer | Venue MLB ID |
| active | boolean | Active status |
| payload | jsonb | Full team object from API |
| retrieved_at | timestamptz | Load timestamp |

### raw_mlb_standings

One row per team standing record.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| season | integer | Season year |
| standings_type | text | regularSeason / wildCard / etc |
| league_id | integer | League MLB ID |
| division_id | integer | Division MLB ID |
| team_id | integer | MLB team ID |
| wins | integer | Wins |
| losses | integer | Losses |
| pct | numeric | Winning percentage |
| games_back | text | Games behind leader |
| wild_card_games_back | text | Wild card games back |
| division_rank | integer | Division rank |
| league_rank | integer | League rank |
| wild_card_rank | integer | Wild card rank |
| streak | text | Current streak |
| payload | jsonb | Full standing record from API |
| retrieved_at | timestamptz | Load timestamp |

### raw_mlb_venues

One row per venue.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| venue_id | integer | MLB venue ID |
| name | text | Venue name |
| city | text | City |
| state | text | State |
| country | text | Country |
| capacity | integer | Seating capacity |
| turf_type | text | Turf type |
| roof_type | text | Roof type |
| left_line | integer | Left field line distance |
| left_center | integer | Left center distance |
| center | integer | Center field distance |
| right_center | integer | Right center distance |
| right_line | integer | Right field line distance |
| latitude | numeric | GPS latitude |
| longitude | numeric | GPS longitude |
| payload | jsonb | Full venue object from API |
| retrieved_at | timestamptz | Load timestamp |

### raw_mlb_rosters

One row per player per team per season from roster endpoint.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| team_id | integer | MLB team ID |
| season | integer | Season year |
| roster_type | text | 40Man / active / fullRoster |
| person_id | integer | MLB player ID |
| full_name | text | Player name |
| jersey_number | text | Jersey number |
| position_code | text | Position code |
| position_name | text | Position name |
| status_code | text | Roster status code |
| payload | jsonb | Full roster entry object |
| retrieved_at | timestamptz | Load timestamp |

### raw_mlb_transactions

One row per roster transaction.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| transaction_id | integer | MLB transaction ID |
| date | date | Transaction date |
| effective_date | date | Effective date |
| type_code | text | Transaction type code |
| type_desc | text | Transaction type description |
| person_id | integer | Player MLB ID |
| person_name | text | Player name |
| from_team_id | integer | Origin team MLB ID |
| to_team_id | integer | Destination team MLB ID |
| description | text | Transaction description |
| payload | jsonb | Full transaction object |
| retrieved_at | timestamptz | Load timestamp |

### raw_mlb_stats

One row per player/team stat retrieval batch.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| entity_type | text | player / team |
| entity_id | integer | MLB player or team ID |
| season | integer | Season year |
| stat_type | text | season / career / yearByYear / gameLog |
| stat_group | text | hitting / pitching / fielding / running |
| payload | jsonb | Full stats response from API |
| retrieved_at | timestamptz | Load timestamp |

### raw_mlb_load_batches

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Unique batch identifier |
| endpoint_family | text | schedule / game_feed / people / teams / etc |
| request_params | jsonb | Request parameters used |
| rows_loaded | integer | Rows inserted |
| loaded_at | timestamptz | Load timestamp |
| status | text | success / failed / partial |
| error_message | text | Error detail if failed |

## Load strategy

- Store full JSON payload alongside extracted scalar keys in every table.
- Track request parameters per batch for full reproducibility.
- Index on entity ID columns (game_pk, person_id, team_id) after load.
- Do not flatten nested payload arrays in the raw layer.
- Use retrieved_at to distinguish historical backfill from current pulls.
