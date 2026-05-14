# ESPN Raw DDL Notes

## Source

- **Provider:** ESPN via unofficial/hidden API (`site.api.espn.com`)
- **Authority:** Community-documented endpoints (no official ESPN developer API for MLB data)
- **Upstream SQL:** None — JSON payloads are the authoritative spec; endpoint schema is volatile
- **DDL files:** `sql/70_tables_raw/026_raw_espn.sql`

## Design strategy

ESPN data comes from unofficial reverse-engineered REST endpoints. Raw ingestion uses a
JSONB-first approach: scalar identifier fields are extracted for indexing and joining,
but the full response payload is always preserved as JSONB. **Do not cast ESPN IDs to
integers** — they are always stored as `TEXT`. Treat all endpoint schemas as potentially
changing without notice.

## Key tables

### `raw.espn_scoreboard`

One row per game event per load from the scoreboard endpoint.

| Column | Type | Notes |
|--------|------|-------|
| load_id | uuid | Batch load identifier |
| event_id | text | ESPN event ID (PK with load_id) |
| game_date | timestamptz | Game date/time |
| season_year | integer | Season year |
| season_type | integer | 1=preseason, 2=regular, 3=postseason |
| status_name | text | STATUS_FINAL / STATUS_IN_PROGRESS / etc. |
| home_team_id | text | ESPN home team ID |
| away_team_id | text | ESPN away team ID |
| home_score | integer | Home score |
| away_score | integer | Away score |
| venue_name | text | Venue name |
| query_date | date | Date queried |
| payload | jsonb | Full event object |
| retrieved_at | timestamptz | Load timestamp |

### `raw.espn_game_summary`

One row per game event per load from the summary endpoint.
Preserves boxscore, play-by-play, and win probability as separate JSONB columns.

| Column | Type | Notes |
|--------|------|-------|
| load_id | uuid | Batch load identifier |
| event_id | text | ESPN event ID (PK with load_id) |
| game_date | date | Game date |
| status_name | text | Game status |
| home_team_id | text | ESPN home team ID |
| away_team_id | text | ESPN away team ID |
| home_score | integer | Home score |
| away_score | integer | Away score |
| boxscore | jsonb | Boxscore section payload |
| plays | jsonb | Play-by-play array payload |
| win_probability | jsonb | Win probability array payload |
| full_payload | jsonb | Complete summary response |
| retrieved_at | timestamptz | Load timestamp |

### `raw.espn_teams`

One row per team per load.

| Column | Type | Notes |
|--------|------|-------|
| load_id | uuid | Batch load identifier |
| team_id | text | ESPN team ID (PK with load_id) |
| abbreviation | text | Team abbreviation |
| display_name | text | Full name |
| location | text | City |
| name | text | Nickname |
| payload | jsonb | Full team object |
| retrieved_at | timestamptz | Load timestamp |

### `raw.espn_rosters`

One row per athlete per team per load.

| Column | Type | Notes |
|--------|------|-------|
| load_id | uuid | Batch load identifier |
| team_id | text | ESPN team ID |
| athlete_id | text | ESPN athlete ID |
| display_name | text | Player name |
| position_abbrev | text | Position abbreviation |
| status_type | text | Active / Injured / etc. |
| payload | jsonb | Full athlete roster entry |
| retrieved_at | timestamptz | Load timestamp |

### `raw.espn_athletes`

One row per athlete per load.

| Column | Type | Notes |
|--------|------|-------|
| load_id | uuid | Batch load identifier |
| athlete_id | text | ESPN athlete ID (PK with load_id) |
| display_name | text | Full name |
| position_abbrev | text | Position |
| active | boolean | Active status |
| payload | jsonb | Full athlete object |
| retrieved_at | timestamptz | Load timestamp |

### `raw.espn_standings`

One row per team per season per load.

| Column | Type | Notes |
|--------|------|-------|
| load_id | uuid | Batch load identifier |
| season_year | integer | Season year |
| season_type | integer | Season type |
| team_id | text | ESPN team ID |
| wins | integer | Wins |
| losses | integer | Losses |
| win_pct | numeric | Win percentage |
| payload | jsonb | Full standings entry |
| retrieved_at | timestamptz | Load timestamp |

### `raw.espn_news`

One row per article per load.

| Column | Type | Notes |
|--------|------|-------|
| load_id | uuid | Batch load identifier |
| article_id | text | ESPN article ID (PK with load_id) |
| headline | text | Headline |
| published_at | timestamptz | Published time |
| payload | jsonb | Full article object |
| retrieved_at | timestamptz | Load timestamp |

### `raw.espn_load_batches`

Metadata table tracking each ESPN API load batch.

| Column | Type | Notes |
|--------|------|-------|
| load_id | uuid | Unique batch ID (PK) |
| endpoint_family | text | scoreboard / game_summary / teams / etc. |
| request_url | text | Full URL used |
| rows_loaded | integer | Rows inserted |
| loaded_at | timestamptz | Load timestamp |
| status | text | success / failed / partial |
| error_message | text | Error detail if failed |

## Load strategy

- Load scoreboard daily for yesterday's games; backfill by date range
- Load game summaries for all finalized games (status_name = STATUS_FINAL)
- Teams and standings: refresh weekly at season start, daily during playoffs
- Generate a `load_id` from `raw.espn_load_batches` before each batch insert

## Schema drift / instability notes

- ESPN endpoints are unofficial and can change or disappear without notice
- Always test endpoints before a new season load; validate against JSONB payload shape
- Do not rely on ESPN data as the primary source for any production metric — use for supplemental scores, news, and roster snapshots
- ESPN athlete IDs do not map directly to MLB player IDs; use `docs/sources/playerid-map` for cross-source joins

## Related docs

- [ESPN source notes](../sources/espn-source-notes.md)
- [ESPN raw schema guide](../sources/espn-raw-schema-guide.md)
- [ESPN SQL DDL](../../sql/70_tables_raw/026_raw_espn.sql)
