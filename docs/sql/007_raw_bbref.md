# Baseball Reference (bbref) Raw DDL Notes

## Source

- **Provider:** Baseball Reference via `pybaseball` wrappers (`batting_stats_bref`, `pitching_stats_bref`, `schedule_and_record`)
- **Authority:** Baseball Reference report pages (scraper-derived outputs, not official SQL schema)
- **Upstream SQL:** None — scraper output column headers are the authoritative spec
- **DDL files:** `sql/70_tables_raw/022_raw_bbref_batting.sql`, `sql/70_tables_raw/023_raw_bbref_pitching.sql`, `sql/70_tables_raw/024_raw_bbref_schedule.sql`

## Design strategy

Baseball Reference data is scraped from report pages. Outputs vary by report type
(batting, pitching, schedule/game log). Raw tables mirror scraper output column layouts.
All tables include a `payload` JSONB column as a safety net for column drift.
Baseball Reference IDs (`bbref_id`) are the natural primary keys for player-level data.

## Key tables

### `raw_bbref_batting`

One row per player per season from the standard batting report.

| Column | Type | Notes |
|--------|------|-------|
| load_id | uuid | Batch load identifier |
| bbref_id | text | Baseball Reference player ID |
| Name | text | Player name |
| Age | integer | Age |
| Team | text | Team abbreviation |
| Season | integer | Season year |
| G | integer | Games |
| PA | integer | Plate appearances |
| AB | integer | At bats |
| R | integer | Runs |
| H | integer | Hits |
| 2B | integer | Doubles |
| 3B | integer | Triples |
| HR | integer | Home runs |
| RBI | integer | RBI |
| SB | integer | Stolen bases |
| CS | integer | Caught stealing |
| BB | integer | Walks |
| SO | integer | Strikeouts |
| BA | numeric | Batting average |
| OBP | numeric | On-base percentage |
| SLG | numeric | Slugging percentage |
| OPS | numeric | OPS |
| OPS_plus | integer | OPS+ |
| TB | integer | Total bases |
| GDP | integer | GIDP |
| HBP | integer | Hit by pitch |
| SH | integer | Sacrifice hits |
| SF | integer | Sacrifice flies |
| IBB | integer | Intentional walks |
| WAR | numeric | Baseball Reference WAR |
| payload | jsonb | Full row from scraper |
| loaded_at | timestamptz | Load timestamp |

### `raw_bbref_pitching`

One row per pitcher per season from the standard pitching report.

| Column | Type | Notes |
|--------|------|-------|
| load_id | uuid | Batch load identifier |
| bbref_id | text | Baseball Reference player ID |
| Name | text | Player name |
| Age | integer | Age |
| Team | text | Team abbreviation |
| Season | integer | Season year |
| W | integer | Wins |
| L | integer | Losses |
| W_L_pct | numeric | Win-loss percentage |
| ERA | numeric | ERA |
| G | integer | Games |
| GS | integer | Games started |
| GF | integer | Games finished |
| CG | integer | Complete games |
| SHO | integer | Shutouts |
| SV | integer | Saves |
| IP | numeric | Innings pitched |
| H | integer | Hits allowed |
| R | integer | Runs allowed |
| ER | integer | Earned runs |
| HR | integer | HR allowed |
| BB | integer | Walks |
| IBB | integer | Intentional walks |
| SO | integer | Strikeouts |
| HBP | integer | Hit batters |
| BK | integer | Balks |
| WP | integer | Wild pitches |
| BF | integer | Batters faced |
| ERA_plus | integer | ERA+ |
| FIP | numeric | FIP |
| WHIP | numeric | WHIP |
| H_9 | numeric | H/9 |
| HR_9 | numeric | HR/9 |
| BB_9 | numeric | BB/9 |
| SO_9 | numeric | SO/9 |
| SO_BB | numeric | SO/BB |
| WAR | numeric | Baseball Reference WAR |
| payload | jsonb | Full row from scraper |
| loaded_at | timestamptz | Load timestamp |

### `raw_bbref_schedule`

One row per game from a team or league schedule/game-log report.

| Column | Type | Notes |
|--------|------|-------|
| load_id | uuid | Batch load identifier |
| team | text | Team abbreviation |
| season | integer | Season year |
| game_num | integer | Game number |
| game_date | date | Game date |
| home_away | text | H=home, A=away |
| opponent | text | Opponent abbreviation |
| result | text | W/L/T |
| runs | integer | Runs scored |
| runs_allowed | integer | Runs allowed |
| innings | integer | Extra innings (null if 9) |
| win_loss_record | text | Record after game |
| rank | integer | Division standing |
| games_back | text | GB |
| winning_pitcher | text | Winning pitcher name |
| losing_pitcher | text | Losing pitcher name |
| save_pitcher | text | Save pitcher (if any) |
| game_duration | text | Duration h:mm |
| night_game | boolean | True if night game |
| attendance | integer | Attendance |
| payload | jsonb | Full row from scraper |
| loaded_at | timestamptz | Load timestamp |

## Load strategy

- Load via `pybaseball.batting_stats_bref(season)`, `pitching_stats_bref(season)` per year
- Schedule data via `pybaseball.schedule_and_record(season, team)` per team per year
- Unique constraint on `(bbref_id, Season, Team)` for batting/pitching
- Unique constraint on `(team, season, game_num)` for schedule

## Scraper / drift notes

- Baseball Reference blocks aggressive scrapers — use `pybaseball` which respects rate limits
- Column layouts can shift when Baseball Reference redesigns report pages
- `bbref_id` values (e.g., `troutmi01`) are stable and suitable for cross-source joining
- Prefer Retrosheet and Statcast for event-level data; use bbref for WAR and historical stat lines

## Related docs

- [Raw DDL source matrix](./raw-ddl-source-matrix.md)
- SQL files: `022_raw_bbref_batting.sql`, `023_raw_bbref_pitching.sql`, `024_raw_bbref_schedule.sql`
