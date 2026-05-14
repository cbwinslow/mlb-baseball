# ESPN Raw Schema Guide

## Strategy

ESPN raw ingestion should use JSONB payload tables keyed by endpoint family. Because ESPN API responses are unofficial, subject to change, and vary by game state, the raw layer should preserve full payloads alongside extracted scalar identifiers. Do not attempt to fully type all ESPN response fields in the raw layer.

## Raw table families

### raw_espn_scoreboard

One row per game entry from the scoreboard endpoint.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| event_id | text | ESPN event ID |
| game_date | timestamptz | Game date/time |
| season_year | integer | Season year |
| season_type | integer | 1=preseason, 2=regular, 3=postseason |
| status_name | text | Game status (STATUS_FINAL, etc) |
| home_team_id | text | ESPN home team ID |
| away_team_id | text | ESPN away team ID |
| home_score | integer | Home team score |
| away_score | integer | Away team score |
| venue_name | text | Venue name |
| query_date | date | Date used in query |
| payload | jsonb | Full event object from scoreboard |
| retrieved_at | timestamptz | Load timestamp |

### raw_espn_game_summary

One row per game summary retrieval.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| event_id | text | ESPN event ID |
| game_date | date | Game date |
| status_name | text | Game status |
| home_team_id | text | ESPN home team ID |
| away_team_id | text | ESPN away team ID |
| home_score | integer | Home team score |
| away_score | integer | Away team score |
| boxscore | jsonb | Boxscore section payload |
| plays | jsonb | Play-by-play array payload |
| win_probability | jsonb | Win probability array payload |
| full_payload | jsonb | Complete summary response |
| retrieved_at | timestamptz | Load timestamp |

### raw_espn_teams

One row per team retrieval.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| team_id | text | ESPN team ID |
| uid | text | ESPN unique identifier |
| slug | text | URL slug |
| abbreviation | text | Team abbreviation |
| display_name | text | Full team name |
| short_display_name | text | Short name |
| location | text | City |
| name | text | Nickname |
| color | text | Primary color hex |
| alternate_color | text | Alternate color hex |
| payload | jsonb | Full team object |
| retrieved_at | timestamptz | Load timestamp |

### raw_espn_rosters

One row per athlete per team retrieval.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| team_id | text | ESPN team ID |
| athlete_id | text | ESPN athlete ID |
| display_name | text | Player name |
| jersey | text | Jersey number |
| position_abbrev | text | Position abbreviation |
| status_type | text | Active/Injured/etc |
| payload | jsonb | Full athlete roster entry object |
| retrieved_at | timestamptz | Load timestamp |

### raw_espn_athletes

One row per athlete retrieval.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| athlete_id | text | ESPN athlete ID |
| uid | text | ESPN unique identifier |
| display_name | text | Full name |
| short_name | text | Short name |
| weight | integer | Weight |
| height | integer | Height |
| age | integer | Age |
| date_of_birth | date | Birth date |
| birth_city | text | Birth city |
| birth_state | text | Birth state |
| birth_country | text | Birth country |
| college | text | College |
| position_abbrev | text | Position abbreviation |
| active | boolean | Active status |
| payload | jsonb | Full athlete object |
| retrieved_at | timestamptz | Load timestamp |

### raw_espn_standings

One row per team per standings retrieval.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| season_year | integer | Season year |
| season_type | integer | Season type |
| team_id | text | ESPN team ID |
| team_abbrev | text | Team abbreviation |
| wins | integer | Wins |
| losses | integer | Losses |
| win_pct | numeric | Win percentage |
| games_back | numeric | Games behind |
| streak | text | Streak string |
| payload | jsonb | Full standings entry object |
| retrieved_at | timestamptz | Load timestamp |

### raw_espn_news

One row per news article.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| article_id | text | ESPN article ID |
| headline | text | Headline |
| description | text | Article description |
| published_at | timestamptz | Published timestamp |
| last_modified_at | timestamptz | Last modified timestamp |
| article_url | text | Article URL |
| payload | jsonb | Full article object |
| retrieved_at | timestamptz | Load timestamp |

### raw_espn_load_batches

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Unique batch identifier |
| endpoint_family | text | scoreboard / game_summary / teams / rosters / athletes / standings / news |
| request_url | text | Full request URL used |
| request_params | jsonb | Request parameters |
| rows_loaded | integer | Rows inserted |
| loaded_at | timestamptz | Load timestamp |
| status | text | success / failed / partial |
| error_message | text | Error detail |

## Load strategy

- Store full JSON payload alongside extracted scalar identifiers in every table.
- Use text type for all ESPN IDs; they are integers in practice but should not be cast without validation.
- Track full request URL per batch for reproducibility and debugging.
- Build ESPN-to-MLB-ID crosswalk table separately; do not embed crosswalk logic in raw tables.
- Index on event_id, team_id, athlete_id after load.
- Accept null scores and status fields for pre-game or live game records.
